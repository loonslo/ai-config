"""Bounded, self-contained machine bundle v1 (independent of sync_core.package)."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import unicodedata
import uuid
import zipfile
import zlib
from typing import Any
from .privacy import private_text, private_metadata

MAX_MEMBERS = 20_000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_RATIO = 1_000
FORMAT = "ai-machine-bundle"
TOP_KEYS = frozenset({"format", "schema_version", "bundle_id", "content_id", "created_at", "tool", "source", "root_hint", "entries", "projects", "exclusions", "warnings", "limits"})
_HEX = re.compile(r"^[0-9a-f]{64}$")


class BundleError(ValueError):
    """The archive is malformed, unsafe or no longer matches its manifest."""


def _member_name(name: str) -> None:
    if not name or len(name) > 240 or name.startswith(("/", "\\")) or "\\" in name:
        raise BundleError("invalid archive member name")
    if re.match(r"^[A-Za-z]:", name) or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise BundleError("invalid archive member name")
    if any(part in {"", ".", ".."} for part in name.split("/")):
        raise BundleError("invalid archive member name")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BundleError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise BundleError("non-finite JSON number")


def _read_limited(handle: Any, limit: int) -> bytes:
    parts: list[bytes] = []
    size = 0
    while True:
        chunk = handle.read(min(64 * 1024, limit - size + 1))
        if not chunk:
            return b"".join(parts)
        size += len(chunk)
        if size > limit:
            raise BundleError("archive member exceeds size limit")
        parts.append(chunk)


def content_id(entries: list[dict[str, Any]]) -> str:
    pairs = sorted((entry["archive_path"], entry["sha256"]) for entry in entries)
    return hashlib.sha256(b"".join(f"{path}\0{sha}\n".encode("utf-8") for path, sha in pairs)).hexdigest()


def _check_manifest(manifest: Any, members: dict[str, zipfile.ZipInfo]) -> None:
    if not isinstance(manifest, dict) or set(manifest) != TOP_KEYS:
        raise BundleError("unknown or missing manifest fields")
    if manifest["format"] != FORMAT or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise BundleError("unsupported bundle format")
    entries = manifest["entries"]
    if not isinstance(entries, list) or len(entries) > MAX_MEMBERS - 1:
        raise BundleError("invalid manifest entries")
    listed: set[str] = set()
    ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not {"id", "archive_path", "sha256", "size"} <= set(entry):
            raise BundleError("invalid manifest entry")
        path, sha, size, entry_id = (entry[key] for key in ("archive_path", "sha256", "size", "id"))
        if not isinstance(path, str) or not isinstance(sha, str) or not _HEX.fullmatch(sha):
            raise BundleError("invalid manifest entry")
        _member_name(path)
        if not path.startswith(("files/", "reports/")) or path in listed or not isinstance(entry_id, str) or entry_id in ids:
            raise BundleError("invalid manifest entry")
        if type(size) is not int or size < 0 or size > MAX_FILE_BYTES:
            raise BundleError("invalid manifest entry size")
        listed.add(path)
        ids.add(entry_id)
    if listed != set(members) - {"manifest.json"}:
        raise BundleError("archive files do not match manifest")
    if not isinstance(manifest["content_id"], str) or manifest["content_id"] != content_id(entries):
        raise BundleError("content identity mismatch")


def validate_bundle(path: Path | str) -> dict[str, Any]:
    """Check central directory, limits, JSON, paths and every file digest."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_MEMBERS:
                raise BundleError("too many archive members")
            members: dict[str, zipfile.ZipInfo] = {}
            folded: set[str] = set()
            total = 0
            for info in infos:
                name = info.orig_filename
                _member_name(name)
                if info.is_dir() or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise BundleError("unsupported archive member")
                if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                    raise BundleError("symbolic links are not allowed")
                key = unicodedata.normalize("NFC", name).casefold()
                if key in folded:
                    raise BundleError("duplicate archive member")
                folded.add(key)
                members[name] = info
                cap = MAX_MANIFEST_BYTES if name == "manifest.json" else MAX_FILE_BYTES
                if info.file_size > cap or info.file_size < 0:
                    raise BundleError("archive member exceeds size limit")
                total += info.file_size
                if total > MAX_TOTAL_BYTES:
                    raise BundleError("archive exceeds total size limit")
                if info.file_size and (not info.compress_size or info.file_size / info.compress_size > MAX_RATIO):
                    raise BundleError("abnormal compression ratio")
            if "manifest.json" not in members:
                raise BundleError("manifest is missing")
            with archive.open("manifest.json") as handle:
                raw = _read_limited(handle, MAX_MANIFEST_BYTES)
            manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_reject_constant)
            _check_manifest(manifest, members)
            for entry in manifest["entries"]:
                with archive.open(entry["archive_path"]) as handle:
                    data = _read_limited(handle, MAX_FILE_BYTES)
                if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                    raise BundleError("archive content does not match manifest")
            return manifest
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise BundleError("invalid or damaged machine bundle") from error


def read_bundle(path: Path | str) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Return validated bytes; callers must treat them as untrusted instructions."""
    manifest = validate_bundle(path)
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        for entry in manifest["entries"]:
            with archive.open(entry["archive_path"]) as handle:
                data = _read_limited(handle, MAX_FILE_BYTES)
            if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise BundleError("archive changed during reading")
            files[entry["archive_path"]] = data
    return manifest, files


class BundleWriter:
    def __init__(self, destination: Path | str, *, source: dict[str, Any] | None = None, root_hint: dict[str, Any] | None = None):
        self.destination = Path(destination)
        self.source = source or {}
        self.root_hint = root_hint or {}
        self.entries: list[dict[str, Any]] = []
        self._files: dict[str, bytes] = {}

    def check_privacy(self, *, projects: list[dict[str, Any]], exclusions: list[dict[str, Any]],
                      warnings: list[dict[str, Any]]) -> None:
        """Check all exported bytes and metadata before preview or publication."""
        metadata = {'source': self.source, 'root_hint': self.root_hint,
                    'entries': self.entries, 'projects': projects,
                    'exclusions': exclusions, 'warnings': warnings,
                    'destination': str(self.destination)}
        if private_metadata(metadata) or any(private_text(data) for data in self._files.values()):
            raise BundleError('private content in migration output')

    def add_file(self, archive_path: str, data: bytes, *, agent: str, instance: str, kind: str,
                 logical_path: str, tier: int = 1, mode: str = "file", restore: str = "auto",
                 project_id: str | None = None, flags: list[str] | None = None,
                 fields: list[str] | None = None, confirm_fields: list[str] | None = None) -> None:
        _member_name(archive_path)
        if not archive_path.startswith("files/") or not isinstance(data, bytes) or len(data) > MAX_FILE_BYTES or archive_path in self._files:
            raise BundleError("invalid file for bundle")
        self._files[archive_path] = data
        self.entries.append({
            "id": f"e{len(self.entries) + 1:04d}", "agent": agent, "instance": instance, "kind": kind,
            "tier": tier, "mode": mode, "logical_path": logical_path, "archive_path": archive_path,
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "restore": restore,
            "project_id": project_id, "flags": flags or [],
        })
        if mode == "fields":
            self.entries[-1]["fields"] = fields or []
            self.entries[-1]["confirm_fields"] = confirm_fields or []

    def add_report(self, name: str, content: str | bytes) -> None:
        archive_path = "reports/" + name
        _member_name(archive_path)
        data = content.encode("utf-8") if isinstance(content, str) else content
        if not isinstance(data, bytes) or len(data) > MAX_FILE_BYTES or archive_path in self._files:
            raise BundleError("invalid report for bundle")
        self._files[archive_path] = data
        self.entries.append({
            "id": f"e{len(self.entries) + 1:04d}", "agent": "report", "instance": "main",
            "kind": "report", "tier": 1, "mode": "file", "logical_path": archive_path,
            "archive_path": archive_path, "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data), "restore": "never", "project_id": None, "flags": [],
        })

    def finalize(self, *, projects: list[dict[str, Any]] | None = None, exclusions: list[dict[str, Any]] | None = None,
                 warnings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if self.destination.exists() or self.destination.is_symlink():
            raise BundleError("bundle destination already exists")
        if len(self._files) + 1 > MAX_MEMBERS or sum(map(len, self._files.values())) > MAX_TOTAL_BYTES:
            raise BundleError("bundle exceeds size limit")
        manifest = {
            "format": FORMAT, "schema_version": 1, "bundle_id": uuid.uuid4().hex,
            "content_id": content_id(self.entries),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "tool": {"name": "ai-config-machine", "version": "0.1.0", "git_commit": None},
            "source": self.source, "root_hint": self.root_hint, "entries": self.entries,
            "projects": projects or [], "exclusions": exclusions or [], "warnings": warnings or [],
            "limits": {"max_members": MAX_MEMBERS, "max_file_bytes": MAX_FILE_BYTES, "max_total_bytes": MAX_TOTAL_BYTES},
        }
        raw = (json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        if len(raw) > MAX_MANIFEST_BYTES:
            raise BundleError("manifest exceeds size limit")
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        partial = self.destination.with_name(self.destination.name + ".partial")
        created = False
        try:
            with partial.open("xb") as handle:
                created = True
                with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=False) as archive:
                    archive.writestr("manifest.json", raw)
                    for name, data in self._files.items():
                        archive.writestr(name, data)
                handle.flush()
                os.fsync(handle.fileno())
            validate_bundle(partial)
            if self.destination.exists() or self.destination.is_symlink():
                raise BundleError("bundle destination already exists")
            os.rename(partial, self.destination)
            return manifest
        finally:
            if created:
                partial.unlink(missing_ok=True)
