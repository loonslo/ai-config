"""Codex snapshot/reference adapter; it never writes native Codex memory."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..transaction import PlannedChanges
from ..utils import digest, read_bytes


def read_export(root: Path) -> dict[str, bytes]:
    if not root.exists():
        raise ValueError(f"Codex memory source missing: {root}")
    result: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Symlink requires manual migration: {path}")
        if path.is_file():
            if path.suffix != ".md":
                raise ValueError(f"Only Markdown Codex exports are supported: {path}")
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def reference_index(project_id: str, files: Mapping[str, bytes], snapshot_id: str) -> bytes:
    lines = ["# Codex memory reference", "", f"Project: `{project_id}`", f"Snapshot: `{snapshot_id}`", "", "Read only the relevant files below:"]
    lines.extend(f"- `{name}` (sha256 `{digest(data)}`)" for name, data in sorted(files.items()))
    return ("\n".join(lines) + "\n").encode("utf-8")


def reference_plan(target: Path, content: bytes, *, state_root: Path | None = None) -> PlannedChanges:
    current = read_bytes(target)
    if current == content:
        return PlannedChanges({}, expected={target: digest(current)}, state_root=state_root, metadata={"adapter": "codex-reference"})
    return PlannedChanges({target: content}, expected={target: digest(current)}, state_root=state_root, metadata={"adapter": "codex-reference"})
