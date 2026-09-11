"""Deterministic three-way memory merging and portable path validation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Mapping

from .utils import canonical_path, digest, nfc, safe_relative

BytesMap = Mapping[str, bytes]


@dataclass(frozen=True)
class MergeConflict:
    path: str
    reason: str
    local_hash: str | None
    shared_hash: str | None
    base_hash: str | None


@dataclass(frozen=True)
class MergeResult:
    files: dict[str, bytes]
    conflicts: tuple[MergeConflict, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.conflicts


_RESERVED = re.compile(r"(?i)^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$")


def validate_file_map(files: BytesMap, *, max_relative_length: int = 240) -> dict[str, bytes]:
    """Normalize and validate a complete merged collection before writing it."""
    normalized: dict[str, bytes] = {}
    seen: dict[str, tuple[str, str]] = {}
    for raw_name, data in files.items():
        name = safe_relative(raw_name)
        if len(name) > max_relative_length:
            raise ValueError(f"Path is too long for portable memory sync: {name}")
        parts = PurePosixPath(name).parts
        for part in parts:
            if any(char in part for char in '<>:"\\|?*') or part.endswith((".", " ")) or _RESERVED.fullmatch(part):
                raise ValueError(f"Filename is not portable to Windows: {name}")
        key = canonical_path(name)
        previous = seen.get(key)
        if previous is not None:
            raise ValueError(f"Unicode/case-insensitive filename collision: {previous[0]} and {raw_name}")
        seen[key] = (raw_name, name)
        normalized[name] = data

    keys = {canonical_path(name): name for name in normalized}
    for name in normalized:
        parts = PurePosixPath(name).parts
        prefix = []
        for part in parts[:-1]:
            prefix.append(part)
            parent_key = canonical_path("/".join(prefix))
            if parent_key in keys:
                raise ValueError(f"File/directory path collision: {keys[parent_key]} and {name}")
    return dict(sorted(normalized.items()))


def three_way_merge(local: BytesMap, shared: BytesMap, base: Mapping[str, str]) -> MergeResult:
    """Merge file presence and content using a previously applied hash baseline.

    A missing base entry means the path did not exist in the common snapshot.
    A known base hash plus one missing side represents a deletion; that deletion
    only wins when the other side is unchanged.  Conflicting results are never
    rendered with conflict markers and are not returned as an applicable batch.
    """
    merged: dict[str, bytes] = {}
    conflicts: list[MergeConflict] = []
    for name in sorted(set(local) | set(shared) | set(base)):
        left = local.get(name)
        right = shared.get(name)
        before = base.get(name)
        left_hash, right_hash = digest(left), digest(right)

        if left_hash == right_hash:
            value = left
        elif before is None:
            if left is None:
                value = right
            elif right is None:
                value = left
            else:
                conflicts.append(MergeConflict(name, "both sides added different content", left_hash, right_hash, before))
                continue
        elif left_hash == before:
            value = right
        elif right_hash == before:
            value = left
        else:
            conflicts.append(MergeConflict(name, "both sides changed the same path", left_hash, right_hash, before))
            continue
        if value is not None:
            merged[name] = value

    if conflicts:
        return MergeResult({}, tuple(conflicts))
    return MergeResult(validate_file_map(merged), ())


def merge(local: BytesMap, shared: BytesMap, base: Mapping[str, str]) -> dict[str, bytes]:
    """Compatibility wrapper that raises instead of returning conflict details."""
    result = three_way_merge(local, shared, base)
    if result.conflicts:
        names = ", ".join(conflict.path for conflict in result.conflicts)
        raise ValueError("Conflicting memory files (both sides preserved): " + names)
    return result.files
