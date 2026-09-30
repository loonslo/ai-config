"""Download and publish the shared configuration source repository.

Three facts are deliberately kept apart, because a user reading "同步成功" must
be able to tell which of them actually happened:

``本机保存``
    A shared value was written into this checkout's working tree — the ``share``
    outcome of ``diff``.  Nothing has left the machine yet.
``远端发布``
    That value was committed *and pushed* to the configuration source remote, so
    another machine can download it.
``本机应用``
    The shared value was written into this machine's tool target files by
    ``sync`` (``sync_core.config_sync``), with backup and read-back verification.

Only ``common/``, ``codex/``, ``claude/`` and ``agents.toml`` are ever committed from here.  A
device's private state, its memory repository and the tool directories are never
touched by this module, and a push is never forced: a diverged source keeps the
local commit and asks the user to resolve it.

Every Git call runs with a hard timeout, a closed stdin and terminal prompting
disabled, so a remote that asks for credentials can never block a sync.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

from .config import absolute
from .utils import SECRET

#: The only paths that may be committed and published from the source checkout.
#: ``agents.toml`` is a single file (shared topic choices per agent).
PUBLISHABLE_PATHS = ("common", "codex", "claude", "agents.toml")


def _publishable(name: str) -> bool:
    return any(name == path or name.startswith(f"{path}/") for path in PUBLISHABLE_PATHS)

_GIT_TIMEOUT = 60.0

#: Never let git ask a human for credentials while a sync is running.
_GIT_ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
    "GCM_INTERACTIVE": "never",
}


class ConfigSourceError(RuntimeError):
    """The configuration source could not be downloaded or published."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def source_root(config: Mapping[str, Any] | Any) -> Path:
    """The local checkout of the shared configuration source.

    A device may record ``config_repo`` to point at a checkout that is not the
    one the scripts were loaded from; otherwise the repository holding the
    shared templates is used.
    """
    raw = getattr(config, "raw", config)
    override = raw.get("config_repo") if isinstance(raw, Mapping) else None
    if override:
        return absolute(override)
    from . import config_sync

    return Path(config_sync.ROOT_FOR_TEMPLATES)


def _run(root: Path, *args: str, check: bool = True, timeout: float = _GIT_TIMEOUT) -> str:
    """Run git and return its stripped stdout; never leak stderr to the user."""
    return _run_raw(root, *args, check=check, timeout=timeout).stdout.strip()


def _run_raw(root: Path, *args: str, check: bool = True, timeout: float = _GIT_TIMEOUT) -> subprocess.CompletedProcess:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            env=_GIT_ENV,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise ConfigSourceError("Git 操作超时或无法执行；本机文件未被修改。", exit_code=3) from error
    if check and completed.returncode:
        # Git stderr may contain a credentialed URL; keep it out of the message.
        raise ConfigSourceError(f"Git 操作失败（{args[0] if args else 'git'}）。", exit_code=3)
    return completed


def is_repository(root: Path) -> bool:
    """Only trust git facts after confirming the directory *is* a repository."""
    return (root / ".git").exists()


def remote_url(root: Path) -> str | None:
    return _run(root, "remote", "get-url", "origin", check=False) or None


def _rev(root: Path, ref: str) -> str | None:
    """Resolve a ref, or ``None`` when it does not exist.

    ``git rev-parse <ref>`` echoes the unresolved argument on stdout even when it
    fails, so a plain call would report a missing branch as present.  The
    ``--verify --quiet`` form is the only one that can be trusted.
    """
    return _run(root, "rev-parse", "--verify", "--quiet", ref, check=False) or None


def head(root: Path) -> str | None:
    return _rev(root, "HEAD")


def current_branch(root: Path) -> str | None:
    return _run(root, "branch", "--show-current", check=False) or None


def _is_ancestor(root: Path, older: str, newer: str) -> bool:
    result = _run_raw(root, "merge-base", "--is-ancestor", older, newer, check=False)
    return result.returncode == 0


def _porcelain_lines(root: Path, *paths: str) -> list[str]:
    """Read ``git status --porcelain`` without losing a significant leading space.

    ``git status`` encodes the index/worktree state in the first two columns and
    a clean-in-index modification starts with a space.  The output is therefore
    read raw and split line by line instead of being stripped as a whole.
    """
    result = _run_raw(root, "status", "--porcelain", "--", *paths, check=False)
    if result.returncode:
        return []
    lines = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        entry = line[3:] if len(line) >= 4 else line.strip()
        lines.append(entry.split(" -> ")[-1].strip())
    return lines


def pending_files(config: Mapping[str, Any] | Any) -> list[str]:
    """Shared files saved locally but not yet committed to the source."""
    root = source_root(config)
    if not is_repository(root):
        return []
    return sorted(set(_porcelain_lines(root, *PUBLISHABLE_PATHS)))


def fetch(config: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Download the shared configuration source (fast-forward only).

    Returns a report instead of raising for the ordinary "nothing to download"
    conditions, so the caller can distinguish "已是最新" from "未配置远端".
    """
    root = source_root(config)
    if not is_repository(root):
        return {"status": "not_configured", "root": str(root), "detail": "配置源目录不是 Git 仓库，跳过下载。"}
    if not remote_url(root):
        return {"status": "not_configured", "root": str(root), "detail": "配置源没有远端地址，跳过下载。"}
    branch = current_branch(root)
    if not branch:
        return {"status": "not_configured", "root": str(root), "detail": "配置源处于分离头指针状态，跳过下载。"}
    before = head(root)
    _run(root, "fetch", "origin", branch)
    remote_ref = _rev(root, f"origin/{branch}")
    if not remote_ref:
        return {"status": "not_configured", "root": str(root), "branch": branch, "detail": f"远端还没有 {branch} 分支，跳过下载。"}
    if remote_ref == before:
        return {"status": "up_to_date", "root": str(root), "branch": branch, "commit": before}
    if _is_ancestor(root, before or "", remote_ref) and before:
        merge = _run_raw(root, "merge", "--ff-only", remote_ref, check=False)
        if merge.returncode:
            return {
                "status": "blocked",
                "root": str(root),
                "branch": branch,
                "commit": before,
                "detail": "配置源有未提交的修改，无法直接快进；先运行 sync --publish 或提交后再下载。",
            }
        return {"status": "updated", "root": str(root), "branch": branch, "before": before, "commit": head(root)}
    return {
        "status": "diverged",
        "root": str(root),
        "branch": branch,
        "commit": remote_ref,
        "detail": "配置源本地提交与远端分叉；双方内容都保留，未强制更新。",
    }


def _staged_paths(root: Path) -> list[str]:
    return sorted({name for name in _run(root, "diff", "--cached", "--name-only", check=False).splitlines() if name.strip()})


def _existing_paths(root: Path) -> list[str]:
    """Only stage paths that exist, so a tool that is not used is not an error."""
    return [name for name in PUBLISHABLE_PATHS if (root / name).exists()]


def _scan_staged(root: Path, staged: list[str]) -> None:
    for name in staged:
        content = _run_raw(root, "show", f":{name}", check=False)
        if content.returncode == 0 and SECRET.search(content.stdout):
            raise ConfigSourceError(f"待发布内容命中敏感信息规则，已停止发布：{name}", exit_code=4)


def _commit_identity(root: Path) -> list[str]:
    """Fall back to a neutral identity so a missing git user never blocks a save."""
    if _run(root, "config", "user.email", check=False):
        return []
    return ["-c", "user.email=ai-config@localhost", "-c", "user.name=ai-config"]


def publish(config: Mapping[str, Any] | Any, *, apply: bool, message: str | None = None) -> dict[str, Any]:
    """Save the shared changes locally and publish them to the source remote.

    A preview only lists the files that would be published.  With ``apply`` the
    publishable paths are committed (本机保存) and then pushed (远端发布); a push
    that loses a race is retried after integrating the remote, and a genuine
    divergence keeps the local commit instead of forcing an overwrite.
    """
    raw = getattr(config, "raw", config)
    root = source_root(raw)
    if not is_repository(root):
        return {"status": "not_configured", "root": str(root), "files": [], "detail": "配置源目录不是 Git 仓库，未发布。"}
    files = pending_files(raw)
    if not files:
        return {
            "status": "nothing_to_publish",
            "root": str(root),
            "files": [],
            "commit": head(root),
            "detail": "配置源没有待发布的共享修改。",
        }
    if not apply:
        return {
            "status": "pending",
            "root": str(root),
            "files": files,
            "written": False,
            "detail": "以下共享修改已保存在本机，尚未发布到配置源远端。",
        }

    _run(root, "add", "--", *_existing_paths(root))
    staged = _staged_paths(root)
    if not staged:
        return {"status": "nothing_to_publish", "root": str(root), "files": [], "commit": head(root), "detail": "没有需要发布的暂存内容。"}
    outside = [name for name in staged if not _publishable(name)]
    if outside:
        raise ConfigSourceError("暂存区包含配置源之外的文件，已停止发布：" + "、".join(outside), exit_code=4)
    _scan_staged(root, staged)
    device = raw.get("device") if isinstance(raw, Mapping) else None
    text = message or f"config: publish shared changes from {device or 'device'}"
    commit_result = _run_raw(root, *_commit_identity(root), "commit", "-m", text, check=False)
    if commit_result.returncode:
        raise ConfigSourceError("共享修改提交失败，已保留在工作区，未推送。", exit_code=1)
    commit = head(root)
    report = {"root": str(root), "files": staged, "commit": commit}
    if not remote_url(root):
        return {**report, "status": "saved_locally", "detail": "配置源没有远端地址：共享修改已提交在本机，未推送。"}
    return {**report, **_push(root, raw)}


def _push(root: Path, raw: Mapping[str, Any], *, retries: int = 3) -> dict[str, Any]:
    branch = current_branch(root)
    if not branch:
        return {"status": "saved_locally", "detail": "配置源处于分离头指针状态：已提交在本机，未推送。"}
    for _ in range(max(1, retries)):
        push = _run_raw(root, "push", "origin", f"HEAD:{branch}", check=False)
        if push.returncode == 0:
            return {"status": "published", "branch": branch, "detail": "共享修改已提交并推送到配置源远端。"}
        _run(root, "fetch", "origin", branch, check=False)
        remote = _rev(root, f"origin/{branch}")
        if remote and _is_ancestor(root, remote, "HEAD"):
            # The remote is behind this commit: another push raced us, retry.
            continue
        if remote and _is_ancestor(root, "HEAD", remote):
            _run(root, "merge", "--ff-only", remote, check=False)
            continue
        raise ConfigSourceError("配置源与远端已分叉，本机提交已保留，未强制推送。", exit_code=4)
    raise ConfigSourceError("配置源推送遇到并发推进，本机提交已保留，稍后重试即可。", exit_code=3)
