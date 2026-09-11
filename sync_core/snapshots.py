"""Immutable memory objects and versioned snapshot manifests."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid
from typing import Any, Mapping, Sequence

from .merge import validate_file_map
from .utils import SECRET, atomic_write, digest, json_bytes, safe_relative, sha256


SCHEMA_VERSION = 1
_ID = re.compile(r"[a-z0-9][a-z0-9_-]*")
_SNAPSHOT_ID = re.compile(r"[a-f0-9]+")


class SnapshotError(ValueError):
    """Raised when a snapshot is missing or fails integrity checks."""


def _manifest_hash(manifest: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return sha256(json_bytes(unsigned))


def _snapshot_path(root: Path, device: str, snapshot_id: str) -> Path:
    if not _ID.fullmatch(device):
        raise SnapshotError("Invalid snapshot device")
    if not _SNAPSHOT_ID.fullmatch(snapshot_id):
        raise SnapshotError("Invalid snapshot id")
    return root / "snapshots" / device / f"{snapshot_id}.json"


def _load_parent(root: Path, device: str, parent_snapshot: str | None) -> dict[str, Any] | None:
    if not parent_snapshot:
        return None
    return load_snapshot(root, parent_snapshot, device=device)


def create_snapshot(
    root: Path,
    *,
    device: str,
    scope: str,
    files: Mapping[str, bytes],
    parent_snapshot: str | None = None,
    tool: str = "claude",
    project_id: str | None = None,
    source_status: str = "normal",
    excluded: Sequence[Mapping[str, str]] = (),
    source_id: str | None = None,
    snapshot_id: str | None = None,
    branch_id: str = "default",
) -> dict[str, Any]:
    """Persist content objects first, then publish one immutable manifest and head."""
    if source_status not in {"normal", "normal_but_empty", "empty", "excluded", "intentionally_excluded"}:
        raise SnapshotError("Unavailable sources cannot publish a normal snapshot")
    if not _ID.fullmatch(scope):
        raise SnapshotError("Invalid snapshot scope")
    if project_id is not None and not _ID.fullmatch(project_id):
        raise SnapshotError("Invalid snapshot project id")
    if source_status == "normal" and not files:
        source_status = "normal_but_empty"
    clean_files = validate_file_map(files)
    decoded: dict[str, str] = {}
    for name, data in clean_files.items():
        try:
            decoded[name] = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SnapshotError(f"Memory file is not UTF-8: {name}") from error
        if SECRET.search(decoded[name]):
            raise SnapshotError(f"Potential secret; review locally: {name}")
    records: list[dict[str, Any]] = []
    for name, data in clean_files.items():
        object_hash = sha256(data)
        object_path = root / "objects" / f"{object_hash}.md"
        if object_path.exists() and object_path.read_bytes() != data:
            raise SnapshotError(f"Immutable object hash mismatch: {object_hash}")
        if not object_path.exists():
            atomic_write(object_path, data)
        records.append({"path": name, "sha256": object_hash, "size": len(data), "object": f"objects/{object_hash}.md"})

    parent = _load_parent(root, device, parent_snapshot)
    previous = {item["path"]: item["sha256"] for item in (parent or {}).get("files", [])}
    deletions = [
        {"path": name, "previous_sha256": old_hash, "parent_snapshot": parent_snapshot}
        for name, old_hash in sorted(previous.items()) if name not in clean_files
    ]
    sid = snapshot_id or uuid.uuid4().hex
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": sid,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "device_id": device,
        "scope": scope,
        "tool": tool,
        "project_id": project_id,
        "source_id": source_id,
        "source_status": source_status,
        "parent_snapshot": parent_snapshot,
        "files": records,
        "deletions": deletions,
        "excluded": list(excluded),
    }
    manifest["manifest_sha256"] = _manifest_hash(manifest)
    target = _snapshot_path(root, device, sid)
    if target.exists():
        raise SnapshotError(f"Snapshot already exists: {sid}")
    atomic_write(target, json_bytes(manifest))
    head = {
        "schema_version": SCHEMA_VERSION,
        "device_id": device,
        "scope": scope,
        "snapshot_id": sid,
        "manifest_sha256": manifest["manifest_sha256"],
        "status": "pending",
    }
    atomic_write(root / "heads" / device / f"{scope}.json", json_bytes(head))
    if project_id:
        if not _ID.fullmatch(branch_id):
            raise SnapshotError("Invalid integrated branch id")
        index = [
            "# Integrated memory index",
            "",
            f"Project: `{project_id}`",
            f"Snapshot: `{sid}`",
            "",
            "This index is deterministic and read-only; source objects are immutable.",
            "",
        ]
        index.extend(f"- `{item['path']}` — `{item['sha256']}`" for item in records)
        atomic_write(root / "integrated" / project_id / branch_id / "MEMORY.md", ("\n".join(index) + "\n").encode("utf-8"))
    return manifest


def mark_head_confirmed(root: Path, device: str, scope: str) -> Path:
    """Mark a head only after its containing Git commit was read back remotely."""
    target = root / "heads" / device / f"{scope}.json"
    if not target.exists():
        raise SnapshotError(f"Snapshot head not found: {device}/{scope}")
    head = json.loads(target.read_text(encoding="utf-8"))
    load_snapshot(root, head["snapshot_id"], device=device)
    head["status"] = "uploaded"
    atomic_write(target, json_bytes(head))
    return target


def mark_all_heads_confirmed(root: Path) -> list[Path]:
    changed: list[Path] = []
    for target in sorted((root / "heads").glob("*/*.json")):
        head = json.loads(target.read_text(encoding="utf-8"))
        if head.get("status") == "uploaded":
            continue
        mark_head_confirmed(root, head["device_id"], head["scope"])
        changed.append(target)
    return changed


def _find_snapshot(root: Path, snapshot_id: str, device: str | None = None) -> Path:
    if not _SNAPSHOT_ID.fullmatch(snapshot_id):
        raise SnapshotError("Invalid snapshot id")
    if device:
        candidate = _snapshot_path(root, device, snapshot_id)
        if candidate.exists():
            return candidate
    candidates = list((root / "snapshots").glob(f"*/{snapshot_id}.json"))
    if len(candidates) != 1:
        raise SnapshotError(f"Snapshot not found or ambiguous: {snapshot_id}")
    return candidates[0]


def load_snapshot(root: Path, snapshot_id: str, *, device: str | None = None, verify_objects: bool = True) -> dict[str, Any]:
    target = _find_snapshot(root, snapshot_id, device)
    manifest = json.loads(target.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("snapshot_id") != snapshot_id:
        raise SnapshotError(f"Unsupported or mismatched snapshot manifest: {snapshot_id}")
    if manifest.get("manifest_sha256") != _manifest_hash(manifest):
        raise SnapshotError(f"Snapshot manifest hash mismatch: {snapshot_id}")
    if verify_objects:
        for item in manifest.get("files", []):
            name = safe_relative(item["path"])
            if name != item["path"]:
                raise SnapshotError(f"Non-canonical snapshot path: {name}")
            object_path = root / item["object"]
            if object_path.resolve().parent != (root / "objects").resolve() or object_path.suffix != ".md":
                raise SnapshotError(f"Unsafe snapshot object: {item['object']}")
            data = object_path.read_bytes()
            if digest(data) != item["sha256"] or len(data) != item["size"]:
                raise SnapshotError(f"Snapshot object hash mismatch: {name}")
    return manifest


def snapshot_files(root: Path, manifest: Mapping[str, Any]) -> dict[str, bytes]:
    result = {}
    for item in manifest.get("files", []):
        object_path = root / item["object"]
        if object_path.resolve().parent != (root / "objects").resolve() or object_path.suffix != ".md":
            raise SnapshotError(f"Unsafe snapshot object: {item.get('object')}")
        data = object_path.read_bytes()
        if digest(data) != item["sha256"]:
            raise SnapshotError(f"Snapshot object hash mismatch: {item['path']}")
        result[item["path"]] = data
    return validate_file_map(result)


def restore_snapshot(root: Path, manifest: Mapping[str, Any], target: Path) -> dict[Path, bytes | None]:
    """Build a safe restore batch without modifying the source or remote head."""
    if target.is_symlink():
        raise SnapshotError(f"Symlink requires manual migration: {target}")
    desired = snapshot_files(root, manifest)
    current: dict[str, bytes] = {}
    if target.exists():
        for path in target.rglob("*"):
            if path.is_symlink():
                raise SnapshotError(f"Symlink requires manual migration: {path}")
            if path.is_file():
                relative = path.relative_to(target).as_posix()
                if path.suffix != ".md":
                    raise SnapshotError(f"Unsupported non-memory file in restore target: {relative}")
                current[relative] = path.read_bytes()
    validate_file_map(current)
    changes: dict[Path, bytes | None] = {}
    for name in sorted(set(current) | set(desired)):
        data = desired.get(name)
        if current.get(name) != data:
            changes[target / name] = data
    from .transaction import PlannedChanges
    return PlannedChanges(
        changes,
        expected={target / name: digest(data) for name, data in current.items()},
        expected_trees={target: {name: digest(data) or "" for name, data in current.items()}},
        metadata={"operation": "restore", "snapshot_id": manifest.get("snapshot_id")},
    )
