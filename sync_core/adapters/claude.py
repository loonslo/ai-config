"""Claude native memory directory adapter."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..merge import validate_file_map
from ..transaction import PlannedChanges
from ..utils import digest, read_bytes


def read_memory(root: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    if not root.exists():
        return result
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Symlink requires manual migration: {path}")
        if path.is_file():
            if path.suffix != ".md":
                raise ValueError(f"Only Markdown memory files are supported: {path}")
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return validate_file_map(result)


def apply_plan(root: Path, desired: Mapping[str, bytes], *, state_root: Path | None = None) -> PlannedChanges:
    current = read_memory(root)
    changes = {root / name: desired.get(name) for name in sorted(set(current) | set(desired)) if current.get(name) != desired.get(name)}
    expected = {root / name: digest(data) for name, data in current.items()}
    return PlannedChanges(changes, expected=expected, expected_trees={root: {name: digest(data) or "" for name, data in current.items()}}, state_root=state_root, metadata={"adapter": "claude"})


def reference_index(project_id: str, files: Mapping[str, bytes]) -> bytes:
    names = sorted(files)
    lines = ["# Claude memory index", "", f"Project: `{project_id}`", "", "Available memory files:"]
    lines.extend(f"- `{name}` (sha256 `{digest(files[name])}`)" for name in names)
    return ("\n".join(lines) + "\n").encode("utf-8")
