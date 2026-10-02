"""Stable, secret-aware reads for supported Markdown memory sources."""
from __future__ import annotations

from pathlib import Path
import time

from .merge import validate_file_map
from .utils import SECRET


def files(root: Path, exclude: list[str] | None = None) -> dict[str, bytes]:
    """Read a complete Markdown directory while checking portable names."""
    if root.is_symlink():
        raise ValueError(f"Symlink not supported: {root}")
    if not root.exists():
        return {}
    result: dict[str, bytes] = {}
    excluded = set(exclude or [])
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Symlink not supported: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative in excluded:
                continue
            if path.suffix != ".md":
                raise ValueError(f"Only memory Markdown is supported: {path}")
            data = path.read_bytes()
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError(f"Memory file is not UTF-8: {path}") from error
            if SECRET.search(text):
                raise ValueError(f"Potential secret; review locally: {path}")
            result[relative] = data
    return validate_file_map(result)


def stable_files(
    root: Path,
    exclude: list[str] | None = None,
    *,
    attempts: int = 3,
    interval: float = 0.05,
) -> dict[str, bytes]:
    """Read twice per attempt so active tool writes are never snapshotted."""
    previous: dict[str, bytes] | None = None
    for attempt in range(attempts):
        current = files(root, exclude)
        if previous is not None and current == previous:
            return current
        previous = current
        if attempt + 1 < attempts:
            time.sleep(interval)
    raise ValueError(f"Source is still being written after {attempts} stable-scan attempts: {root}")
