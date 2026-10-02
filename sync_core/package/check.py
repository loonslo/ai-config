"""Read-only, bounded inspection of directory and ZIP migration packages."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import stat
import unicodedata
import zipfile
from types import MappingProxyType
from typing import Any, Mapping

from .format import PackageFormatError, parse_manifest, validate_manifest


MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_OBJECT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_PACKAGE_MEMBERS = 10_001
_OBJECT_MEMBER = re.compile(r"^objects/([a-f0-9]{64})\.bin$")
_REPARSE_POINT = 0x0400


class PackageCheckError(ValueError):
    """A package is malformed, unsafe to read, or exceeds inspection limits."""


@dataclass(frozen=True)
class CheckedPackage:
    manifest: Mapping[str, Any]
    payloads: Mapping[str, bytes] = field(repr=False)
    validation: Mapping[str, Any]
    format: str
    total_bytes: int

    @property
    def importable(self) -> bool:
        return self.validation.get("status") == "valid"

    def public_summary(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "package_id": self.manifest["package_id"],
            "content_id": self.validation["content_id"],
            "entry_count": self.validation["entry_count"],
            "object_count": self.validation["object_count"],
            "total_bytes": self.total_bytes,
            "status": self.validation["status"],
            "unsupported_adapters": list(self.validation["unsupported_adapters"]),
            "parent_status": self.validation["parent_status"],
        }


def _collision_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _check_unique_names(names: list[str]) -> None:
    exact: set[str] = set()
    normalized: dict[str, str] = {}
    for name in names:
        if name in exact:
            raise PackageCheckError(f"Package contains a duplicate path: {name!r}")
        exact.add(name)
        key = _collision_key(name)
        previous = normalized.get(key)
        if previous is not None and previous != name:
            raise PackageCheckError(f"Package contains a case or Unicode path collision: {previous!r}, {name!r}")
        normalized[key] = name


def _reject_reparse(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as error:
        raise PackageCheckError(f"Cannot inspect package path: {path.name}") from error
    attributes = getattr(info, "st_file_attributes", 0)
    if stat.S_ISLNK(info.st_mode) or bool(attributes & _REPARSE_POINT) or bool(getattr(path, "is_junction", lambda: False)()):
        raise PackageCheckError(f"Links and reparse points are not allowed in a package: {path.name}")


def _read_regular_file(path: Path, *, limit: int) -> bytes:
    _reject_reparse(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or bool(getattr(before, "st_file_attributes", 0) & _REPARSE_POINT):
        raise PackageCheckError(f"Package member is not a regular file: {path.name}")
    if before.st_size > limit:
        raise PackageCheckError(f"Package member exceeds the size limit: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise PackageCheckError(f"Package member is not a regular file: {path.name}")
            content = stream.read(limit + 1)
            after_open = os.fstat(stream.fileno())
        after_path = path.lstat()
    except OSError as error:
        raise PackageCheckError(f"Cannot read package member: {path.name}") from error
    if len(content) > limit:
        raise PackageCheckError(f"Package member exceeds the size limit: {path.name}")
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if identity(opened) != identity(after_open) or identity(before) != identity(after_path) or len(content) != after_path.st_size:
        raise PackageCheckError(f"Package member changed while being read: {path.name}")
    return content


def _expected_objects(manifest: Mapping[str, Any]) -> set[str]:
    objects = manifest.get("objects")
    if not isinstance(objects, list):
        raise PackageCheckError("Manifest objects must be an array")
    if len(objects) + 1 > MAX_PACKAGE_MEMBERS:
        raise PackageCheckError("Package has too many members")
    result: set[str] = set()
    for item in objects:
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            raise PackageCheckError("Manifest contains an invalid object record")
        path = item["path"]
        if not _OBJECT_MEMBER.fullmatch(path):
            raise PackageCheckError("Manifest contains an unsafe object path")
        if path in result:
            raise PackageCheckError(f"Manifest contains a duplicate object path: {path}")
        result.add(path)
    if len(result) + 1 > MAX_PACKAGE_MEMBERS:
        raise PackageCheckError("Package has too many members")
    return result


def _read_zip_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo, *, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        with archive.open(member, "r") as stream:
            while True:
                chunk = stream.read(min(64 * 1024, limit + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise PackageCheckError(f"Archive member exceeds the size limit: {member.filename}")
                chunks.append(chunk)
    except PackageCheckError:
        raise
    except (OSError, RuntimeError, EOFError, zipfile.BadZipFile) as error:
        raise PackageCheckError(f"Archive member is damaged: {member.filename}") from error
    if total != member.file_size:
        raise PackageCheckError(f"Archive member size does not match its directory entry: {member.filename}")
    return b"".join(chunks)


def _check_payload_limits(payloads: Mapping[str, bytes]) -> int:
    total = 0
    for path, content in payloads.items():
        if len(content) > MAX_OBJECT_BYTES:
            raise PackageCheckError(f"Object exceeds the per-file size limit: {path}")
        total += len(content)
        if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise PackageCheckError("Package exceeds the total uncompressed size limit")
    return total


def _inspect_directory(path: Path) -> tuple[dict[str, Any], dict[str, bytes], int]:
    _reject_reparse(path)
    if not path.is_dir():
        raise PackageCheckError("Package path is not a directory")
    root_before = path.lstat()
    try:
        root_names = [entry.name for entry in os.scandir(path)]
    except OSError as error:
        raise PackageCheckError("Cannot read package directory") from error
    _check_unique_names(root_names)
    if set(root_names) != {"manifest.json", "objects"}:
        raise PackageCheckError("Directory package must contain only manifest.json and objects/")
    objects_dir = path / "objects"
    _reject_reparse(objects_dir)
    if not objects_dir.is_dir():
        raise PackageCheckError("Directory package objects/ must be an ordinary directory")
    objects_before = objects_dir.lstat()

    manifest_bytes = _read_regular_file(path / "manifest.json", limit=MAX_MANIFEST_BYTES)
    try:
        manifest = parse_manifest(manifest_bytes)
    except PackageFormatError as error:
        raise PackageCheckError(str(error)) from error
    expected = _expected_objects(manifest)
    try:
        object_entries = list(os.scandir(objects_dir))
    except OSError as error:
        raise PackageCheckError("Cannot read package objects directory") from error
    _check_unique_names([entry.name for entry in object_entries])
    if len(object_entries) + 1 > MAX_PACKAGE_MEMBERS:
        raise PackageCheckError("Package has too many members")
    if any(entry.name != Path(entry.name).name or not re.fullmatch(r"[a-f0-9]{64}\.bin", entry.name) for entry in object_entries):
        raise PackageCheckError("Package objects directory contains an unsafe member name")
    actual = {f"objects/{entry.name}" for entry in object_entries}
    if actual != expected:
        raise PackageCheckError("Directory package object set does not match its manifest")

    payloads: dict[str, bytes] = {}
    for entry in object_entries:
        member = objects_dir / entry.name
        _reject_reparse(member)
        if not entry.is_file(follow_symlinks=False):
            raise PackageCheckError(f"Package object is not a regular file: {entry.name}")
        payloads[f"objects/{entry.name}"] = _read_regular_file(member, limit=MAX_OBJECT_BYTES)
    try:
        root_after = path.lstat()
        objects_after = objects_dir.lstat()
        final_root_names = [entry.name for entry in os.scandir(path)]
        final_object_names = [entry.name for entry in os.scandir(objects_dir)]
    except OSError as error:
        raise PackageCheckError("Package directory changed while being checked") from error
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if (
        identity(root_before) != identity(root_after)
        or identity(objects_before) != identity(objects_after)
        or set(final_root_names) != {"manifest.json", "objects"}
        or set(final_object_names) != {entry.name for entry in object_entries}
    ):
        raise PackageCheckError("Package directory changed while being checked")
    total = len(manifest_bytes) + _check_payload_limits(payloads)
    if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise PackageCheckError("Package exceeds the total uncompressed size limit")
    return manifest, payloads, total


def _inspect_archive(path: Path) -> tuple[dict[str, Any], dict[str, bytes], int]:
    _reject_reparse(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise PackageCheckError("Archive package must be a regular file")
    if info.st_size > MAX_ARCHIVE_BYTES:
        raise PackageCheckError("Archive exceeds the compressed file size limit")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            opened_archive = os.fstat(archive.fp.fileno())
            file_identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
            if file_identity(info) != file_identity(opened_archive):
                raise PackageCheckError("Archive changed while it was being opened")
            members = archive.infolist()
            if len(members) > MAX_PACKAGE_MEMBERS:
                raise PackageCheckError("Package has too many members")
            names = [member.filename for member in members]
            _check_unique_names(names)
            declared_total = 0
            for member in members:
                name = member.filename
                if member.is_dir() or "\\" in name or "\x00" in name or (name != "manifest.json" and not _OBJECT_MEMBER.fullmatch(name)):
                    raise PackageCheckError(f"Archive contains an unsafe member path: {name!r}")
                if member.flag_bits & 0x1:
                    raise PackageCheckError(f"Encrypted archive member is not supported: {name}")
                file_type = stat.S_IFMT(member.external_attr >> 16)
                if file_type not in {0, stat.S_IFREG}:
                    raise PackageCheckError(f"Links and special files are not allowed in an archive: {name}")
                if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise PackageCheckError(f"Unsupported compression method for archive member: {name}")
                limit = MAX_MANIFEST_BYTES if name == "manifest.json" else MAX_OBJECT_BYTES
                if member.file_size < 0 or member.file_size > limit:
                    raise PackageCheckError(f"Archive member exceeds the size limit: {name}")
                declared_total += member.file_size
                if declared_total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise PackageCheckError("Package exceeds the total uncompressed size limit")
            if "manifest.json" not in names:
                raise PackageCheckError("Archive has no manifest.json")
            manifest_info = next(member for member in members if member.filename == "manifest.json")
            manifest_bytes = _read_zip_member(archive, manifest_info, limit=MAX_MANIFEST_BYTES)
            try:
                manifest = parse_manifest(manifest_bytes)
            except PackageFormatError as error:
                raise PackageCheckError(str(error)) from error
            expected = _expected_objects(manifest)
            if set(names) != expected | {"manifest.json"}:
                raise PackageCheckError("Archive member set does not match its manifest")
            info_by_name = {member.filename: member for member in members}
            payloads = {
                name: _read_zip_member(archive, info_by_name[name], limit=MAX_OBJECT_BYTES)
                for name in sorted(expected)
            }
            closed_archive = os.fstat(archive.fp.fileno())
            final_path_info = path.lstat()
            if file_identity(opened_archive) != file_identity(closed_archive) or file_identity(info) != file_identity(final_path_info):
                raise PackageCheckError("Archive changed while it was being checked")
    except PackageCheckError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError, ValueError) as error:
        raise PackageCheckError("Archive is damaged or cannot be read") from error
    total = len(manifest_bytes) + _check_payload_limits(payloads)
    if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise PackageCheckError("Package exceeds the total uncompressed size limit")
    return manifest, payloads, total


def check_package(
    path: Path,
    *,
    supported_adapters: Mapping[str, int] | None = None,
    known_content_ids: set[str] | frozenset[str] = frozenset(),
) -> CheckedPackage:
    """Read a package without extracting it and verify every member and digest.

    Unsupported adapters are returned as a valid-but-not-importable result so a
    UI can explain the compatibility gap. Structural and integrity failures raise
    ``PackageCheckError`` and never modify the package or local configuration.
    """
    package_path = Path(path).expanduser()
    if not package_path.exists():
        raise PackageCheckError("Package does not exist")
    if package_path.is_dir():
        format_name = "directory"
        manifest, payloads, total = _inspect_directory(package_path)
    elif package_path.suffix.lower() == ".aiconfig" and package_path.is_file():
        format_name = "archive"
        manifest, payloads, total = _inspect_archive(package_path)
    else:
        raise PackageCheckError("Choose a package directory or a .aiconfig archive")
    try:
        validation = validate_manifest(
            manifest,
            payloads,
            supported_adapters=supported_adapters,
            known_content_ids=known_content_ids,
        )
    except PackageFormatError as error:
        raise PackageCheckError(str(error)) from error
    return CheckedPackage(
        manifest=MappingProxyType(manifest),
        payloads=MappingProxyType(payloads),
        validation=MappingProxyType(validation),
        format=format_name,
        total_bytes=total,
    )
