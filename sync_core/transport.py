"""Conservative Git transport for the dedicated private memory repository."""
from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
import subprocess
from typing import Iterable

from .utils import SECRET


class TransportPending(RuntimeError):
    """The remote advanced or diverged; local data remains pending."""


@dataclass(frozen=True)
class PushResult:
    status: str
    commit: str | None
    files: tuple[str, ...]
    detail: str | None = None


_ROOTS = {"registry", "objects", "snapshots", "heads", "integrated", "handoffs", "claude", "codex"}


def _run(root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode:
        # Git stderr can include credential-helper or remote URLs.  Keep it out
        # of the sync log and user-facing error by default.
        raise RuntimeError(f"Git operation failed: {args[0] if args else 'git'} (exit {completed.returncode})")
    return completed.stdout.strip()


def publishable_paths(root: Path) -> list[str]:
    result: list[str] = []
    if not root.exists():
        raise ValueError(f"Memory repository does not exist: {root}")
    def check_name(relative: Path) -> None:
        parts = relative.parts
        if parts and parts[0] in {".sync-state", ".ai-sync"}:
            return
        allowed = relative.name in {"README.md", ".gitignore"} or (parts and parts[0] in _ROOTS)
        if not allowed:
            raise ValueError(f"Unexpected file in memory repository: {relative.as_posix()}")
        if relative.suffix not in {".md", ".json"} and relative.name not in {".gitignore"}:
            raise ValueError(f"Unexpected file type in memory repository: {relative.as_posix()}")
        if parts[0] == "objects" and (not re.fullmatch(r"[0-9a-f]{64}\.md", relative.name)):
            raise ValueError(f"Invalid immutable object name: {relative.as_posix()}")

    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            raise ValueError(f"Unexpected symlink: {path}")
        if not path.is_file():
            continue
        parts = relative.parts
        if parts and parts[0] in {".sync-state", ".ai-sync"}:
            continue
        check_name(relative)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"Memory repository file is not UTF-8: {relative.as_posix()}") from error
        if SECRET.search(content):
            raise ValueError(f"Potential secret; review locally: {relative.as_posix()}")
        result.append(relative.as_posix())
    for name in _run(root, "ls-files", "--deleted", "-z", check=False).split("\x00"):
        if not name:
            continue
        relative = Path(name)
        if not (root / relative).exists():
            check_name(relative)
            result.append(relative.as_posix())
    return sorted(result)


def scan_history(root: Path) -> None:
    """Reject secrets already present in commits that a push could expose."""
    commits = _run(root, "rev-list", "--all", check=False).splitlines()
    for commit in commits:
        names = _run(root, "ls-tree", "-r", "--name-only", commit, check=False).splitlines()
        for name in names:
            if Path(name).suffix not in {".md", ".json", ".toml", ".txt"}:
                continue
            result = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{name}"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                content = result.stdout.decode("utf-8", errors="replace")
                if SECRET.search(content):
                    raise ValueError(f"Potential secret in Git history; push blocked: {name}")


class GitTransport:
    def __init__(self, root: Path) -> None:
        self.root = root

    def validate(self) -> None:
        top = Path(_run(self.root, "rev-parse", "--show-toplevel")).resolve()
        if top != self.root.resolve():
            raise ValueError("memory_repo must be the repository root")

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            subprocess.run(["git", "init", "-b", "main", str(self.root)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def clean(self) -> bool:
        return not bool(_run(self.root, "status", "--porcelain"))

    def has_remote(self) -> bool:
        return bool(_run(self.root, "remote", "get-url", "origin", check=False))

    def ensure_clean(self) -> None:
        if not self.clean():
            raise ValueError("Memory repository has local changes; preserve or commit them before transport")

    def commit_pending(self, message: str = "Sync automatic memory") -> tuple[str, tuple[str, ...]]:
        self.validate()
        scan_history(self.root)
        paths = publishable_paths(self.root)
        if paths:
            _run(self.root, "add", "--all", "--", *paths)
        staged = tuple(filter(None, _run(self.root, "diff", "--cached", "--name-only").splitlines()))
        if staged:
            _run(self.root, "commit", "-m", message)
        commit = _run(self.root, "rev-parse", "HEAD", check=False) or None
        return commit, staged

    def remote_head(self) -> str | None:
        output = _run(self.root, "ls-remote", "origin", "refs/heads/main", check=False)
        return output.split()[0] if output else None

    def fetch_remote(self) -> str | None:
        """Fetch the remote tip before using local graph ancestry checks."""
        if not self.has_remote():
            return None
        # An initialized bare repository has no branch yet.  That is a
        # normal first-publish condition, not a network failure.
        advertised = self.remote_head()
        if not advertised:
            return None
        _run(self.root, "fetch", "origin", "main")
        return _run(self.root, "rev-parse", "refs/remotes/origin/main", check=False) or advertised

    def _is_ancestor(self, older: str, newer: str) -> bool:
        return subprocess.run(["git", "-C", str(self.root), "merge-base", "--is-ancestor", older, newer], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

    def reconcile_remote(self) -> None:
        remote = self.fetch_remote()
        if not remote:
            return
        local = _run(self.root, "rev-parse", "HEAD")
        if remote == local or self._is_ancestor(remote, local):
            return
        if self._is_ancestor(local, remote):
            _run(self.root, "merge", "--ff-only", "FETCH_HEAD")
            return
        raise TransportPending("Remote and local memory histories diverged; local commit is pending")

    def push_confirmed(self, retries: int = 3) -> PushResult:
        self.validate()
        commit, files = self.commit_pending()
        for _ in range(retries):
            self.reconcile_remote()
            commit = _run(self.root, "rev-parse", "HEAD")
            result = subprocess.run(["git", "-C", str(self.root), "push", "-u", "origin", "HEAD:main"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            if result.returncode == 0:
                remote = self.fetch_remote()
                if not remote or not self._is_ancestor(commit, remote):
                    raise TransportPending("Push returned but remote confirmation did not include the local commit")
                return PushResult("uploaded", commit, files)
            # A race with a newly advanced remote is handled by the next
            # iteration; divergent histories stay pending and are never forced.
        raise TransportPending("Remote advanced during push; local snapshot is pending")

    def pull_ff_only(self) -> str:
        self.validate()
        self.ensure_clean()
        _run(self.root, "pull", "--ff-only")
        return _run(self.root, "rev-parse", "HEAD", check=False)
