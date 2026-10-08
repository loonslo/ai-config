"""Portable path identities and workspace-root mapping."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess


def _windows(os_name: str) -> bool:
    return os_name.casefold() in {"windows", "win32", "nt"}


def norm(path: str | os.PathLike[str], os_name: str) -> str:
    """Normalize spelling without consulting the filesystem."""
    value = os.fspath(path)
    if _windows(os_name):
        if value.startswith("\\\\?\\UNC\\"):
            value = "//" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
    value = value.replace("\\", "/")
    unc = value.startswith("//")
    value = re.sub(r"/+", "/", value)
    if unc:
        value = "/" + value
    if re.match(r"^[A-Za-z]:", value):
        value = value[0].lower() + value[1:]
    if value not in {"/", "//"} and not re.fullmatch(r"[a-zA-Z]:/", value):
        value = value.rstrip("/")
    return value


def same_path(left: str | os.PathLike[str], right: str | os.PathLike[str], os_name: str) -> bool:
    a, b = norm(left, os_name), norm(right, os_name)
    return a.casefold() == b.casefold() if _windows(os_name) else a == b


def derive_project_dir(native_path: str | os.PathLike[str]) -> str | None:
    """Claude's simple directory encoding; long hashed names are unsupported."""
    result = "".join(char if char.isalnum() else "-" for char in os.fspath(native_path))
    return result if len(result) <= 200 else None


def git_root(path: str | os.PathLike[str]) -> Path:
    """Return the primary checkout for a worktree, otherwise its Git root."""
    folder = Path(path).resolve()
    if not folder.is_dir():
        folder = folder.parent
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=folder, check=True,
            capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL,
        ).stdout.strip()
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=folder, check=True, capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return folder
    common_path = Path(common)
    if common_path.name == ".git" and common_path.parent.is_dir():
        return common_path.parent.resolve()
    return Path(top).resolve()


@dataclass(frozen=True)
class RootMap:
    """Longest-prefix mapping; Windows-to-Windows has an implicit identity."""

    rules: tuple[tuple[str, str], ...] = ()
    source_os: str = "windows"
    target_os: str = "windows"

    def map(self, path: str | os.PathLike[str]) -> str | None:
        source = norm(path, self.source_os)
        compare = source.casefold() if _windows(self.source_os) else source
        matches: list[tuple[int, str, str]] = []
        for old, new in self.rules:
            root = norm(old, self.source_os)
            key = root.casefold() if _windows(self.source_os) else root
            if compare == key or compare.startswith(key.rstrip("/") + "/"):
                matches.append((len(key), root, norm(new, self.target_os)))
        if matches:
            _, old, new = max(matches, key=lambda item: item[0])
            return new.rstrip("/") + source[len(old):] if source != old else new
        if _windows(self.source_os) and _windows(self.target_os):
            return source
        return None


def real_case(path: str | os.PathLike[str]) -> Path:
    """Use actual spelling of existing components without resolving links."""
    requested = Path(path)
    if not requested.is_absolute():
        raise ValueError("real_case requires an absolute path")
    current = Path(requested.anchor)
    for part in requested.parts[1:]:
        if current.is_symlink():
            raise ValueError("symbolic link in target path")
        if current.is_dir():
            with os.scandir(current) as children:
                actual = next((entry.name for entry in children if entry.name.casefold() == part.casefold()), part)
        else:
            actual = part
        current /= actual
    if current.is_symlink():
        raise ValueError("symbolic link in target path")
    return current
