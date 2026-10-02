"""Build and atomically publish self-contained offline migration packages."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
import zipfile
from typing import Any, Mapping
from urllib.parse import urlsplit

from .format import compute_content_id, validate_manifest
from .policy import CollectionReport, collect_portable_config, select_portable_sources


class PackageExportError(RuntimeError):
    """The selected sources or destination are not safe to export."""


@dataclass(frozen=True)
class PackageExportResult:
    path: Path
    format: str
    package_id: str
    content_id: str
    entry_count: int
    object_count: int


def _portable_agent_ids(report: CollectionReport) -> list[str]:
    result = {
        urlsplit(entry.logical_source).netloc
        for entry in report.entries
        if urlsplit(entry.logical_source).scheme == "settings"
    }
    for entry in report.entries:
        if entry.data_type != "agent_declaration":
            continue
        try:
            value = json.loads(entry.content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if entry.logical_source.endswith("/declarations.json"):
            result.update(
                item["profile"] for item in value.get("instances", [])
                if isinstance(item, dict) and isinstance(item.get("profile"), str)
            )
        elif entry.logical_source.endswith("/agents-registry.json") and isinstance(value, dict):
            result.update(key for key in value if isinstance(key, str))
    return sorted(result)


def build_package_manifest(
    report: CollectionReport,
    *,
    package_id: str | None = None,
    created_at: datetime | None = None,
    parent_content_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Build and validate manifest/object bytes without writing to disk."""
    if not report.entries:
        raise PackageExportError("No portable configuration entries were collected")
    if report.review_required or report.unsupported:
        raise PackageExportError("Review local paths or unsupported sources before exporting")

    object_bytes: dict[str, bytes] = {}
    object_records: list[dict[str, Any]] = []
    entry_records: list[dict[str, Any]] = []
    adapters: dict[str, int] = {}
    sources: set[str] = set()
    for entry in report.entries:
        if entry.logical_source in sources:
            raise PackageExportError(f"Duplicate portable source: {entry.logical_source}")
        sources.add(entry.logical_source)
        previous_version = adapters.setdefault(entry.adapter_id, entry.adapter_version)
        if previous_version != entry.adapter_version:
            raise PackageExportError(f"One package cannot contain multiple versions of adapter {entry.adapter_id}")
        digest = hashlib.sha256(entry.content).hexdigest()
        object_path = f"objects/{digest}.bin"
        existing = object_bytes.get(object_path)
        if existing is not None and existing != entry.content:
            raise PackageExportError("SHA-256 object collision detected")
        if existing is None:
            object_bytes[object_path] = entry.content
            object_records.append({"path": object_path, "sha256": digest, "size": len(entry.content)})
        entry_records.append({
            "logical_source": entry.logical_source,
            "data_type": entry.data_type,
            "adapter_id": entry.adapter_id,
            "adapter_version": entry.adapter_version,
            "object_path": object_path,
        })

    exclusion_by_source: dict[str, dict[str, str]] = {}
    for issue in (*report.exclusions, *report.unsupported, *report.review_required):
        exclusion_by_source.setdefault(issue.logical_source, {
            "logical_source": issue.logical_source,
            "category": issue.category,
        })
    exclusions = [exclusion_by_source[source] for source in sorted(exclusion_by_source)]
    overlap = sources & set(exclusion_by_source)
    if overlap:
        raise PackageExportError(f"A source cannot be included and excluded: {sorted(overlap)[0]}")

    stamp = created_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise PackageExportError("created_at must include a timezone")
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "package_id": package_id or uuid.uuid4().hex,
        "content_id": "0" * 64,
        "parent_content_id": parent_content_id,
        "created_at": stamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": {
            "data_types": sorted({entry.data_type for entry in report.entries}),
            "agent_ids": _portable_agent_ids(report),
        },
        "adapters": [{"id": adapter_id, "version": version} for adapter_id, version in sorted(adapters.items())],
        "objects": sorted(object_records, key=lambda item: item["path"]),
        "entries": sorted(entry_records, key=lambda item: (item["logical_source"], item["data_type"])),
        "dependencies": [],
        "exclusions": exclusions,
    }
    manifest["content_id"] = compute_content_id(manifest)
    validation = validate_manifest(
        manifest,
        object_bytes,
        supported_adapters=adapters,
    )
    if validation["status"] != "valid":
        raise PackageExportError("Generated package did not pass its own format validation")
    return manifest, object_bytes


def _write_file(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _prepare_destination(path: Path) -> tuple[Path, Path]:
    target = Path(path).expanduser().absolute()
    parent = target.parent
    if not parent.is_dir():
        raise PackageExportError("Export destination parent must already exist")
    if target.exists() or target.is_symlink():
        raise PackageExportError("Export destination already exists; choose a new path")
    return target, parent


def _check_sources_unchanged(
    config: Mapping[str, Any],
    store_root: Path,
    expected: CollectionReport,
    selected_sources: list[str] | tuple[str, ...] | None = None,
) -> None:
    from .extensions import KINDS
    kinds = sorted({kind for kind, spec in KINDS.items() for item in (*expected.entries, *expected.exclusions) if urlsplit(item.logical_source).scheme == spec[0]})
    current = collect_portable_config(config, store_root, extension_kinds=kinds)
    if selected_sources is not None:
        current = select_portable_sources(current, selected_sources)
    if current != expected:
        raise PackageExportError("Allowlisted source content changed during export; no package was published")


def _result(path: Path, format_name: str, manifest: Mapping[str, Any]) -> PackageExportResult:
    return PackageExportResult(
        path=path,
        format=format_name,
        package_id=manifest["package_id"],
        content_id=manifest["content_id"],
        entry_count=len(manifest["entries"]),
        object_count=len(manifest["objects"]),
    )


def export_directory(
    report: CollectionReport,
    destination: Path,
    *,
    config: Mapping[str, Any],
    store_root: Path,
    parent_content_id: str | None = None,
    selected_sources: list[str] | tuple[str, ...] | None = None,
) -> PackageExportResult:
    """Publish a directory package with content-addressed, self-contained objects."""
    target, parent = _prepare_destination(destination)
    manifest, objects = build_package_manifest(report, parent_content_id=parent_content_id)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=parent))
    try:
        object_root = stage / "objects"
        object_root.mkdir()
        for relative, content in objects.items():
            _write_file(stage / relative, content)
        _write_file(stage / "manifest.json", _manifest_bytes(manifest))
        _check_sources_unchanged(config, store_root, report, selected_sources)
        if target.exists() or target.is_symlink():
            raise PackageExportError("Export destination appeared during export; it was left untouched")
        os.rename(stage, target)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise
    return _result(target, "directory", manifest)


def export_archive(
    report: CollectionReport,
    destination: Path,
    *,
    config: Mapping[str, Any],
    store_root: Path,
    parent_content_id: str | None = None,
    selected_sources: list[str] | tuple[str, ...] | None = None,
) -> PackageExportResult:
    """Publish a single-file .aiconfig ZIP without replacing an existing file."""
    target, parent = _prepare_destination(destination)
    if target.suffix.lower() != ".aiconfig":
        raise PackageExportError("Archive destination must use the .aiconfig extension")
    manifest, objects = build_package_manifest(report, parent_content_id=parent_content_id)
    fd, stage_name = tempfile.mkstemp(prefix=f".{target.name}.staging-", suffix=".tmp", dir=parent)
    os.close(fd)
    stage = Path(stage_name)
    try:
        with zipfile.ZipFile(stage, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("manifest.json", _manifest_bytes(manifest))
            for relative, content in sorted(objects.items()):
                archive.writestr(relative, content)
        with stage.open("r+b") as stream:
            os.fsync(stream.fileno())
        _check_sources_unchanged(config, store_root, report, selected_sources)
        if target.exists() or target.is_symlink():
            raise PackageExportError("Export destination appeared during export; it was left untouched")
        # A same-directory hard link is an atomic, no-overwrite publication.
        os.link(stage, target)
    except Exception:
        stage.unlink(missing_ok=True)
        raise
    stage.unlink(missing_ok=True)
    return _result(target, "archive", manifest)
