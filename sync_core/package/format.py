"""Strict v1 package manifest parsing and content-integrity validation."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit


FORMAT_VERSION = 1
DATA_TYPES = frozenset({
    "rule_file",
    "shared_setting",
    "agent_declaration",
    "skill_file",
    "mcp_config",
    "memory_snapshot",
    "handoff_record",
})
EXCLUSION_CATEGORIES = frozenset({"sensitive", "protected", "unsupported", "local_only", "user_excluded"})
_HEX_32 = re.compile(r"^[a-f0-9]{32}$")
_HEX_64 = re.compile(r"^[a-f0-9]{64}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_URI_SAFE = re.compile(r"^[A-Za-z0-9._~%:/@+-]+$")
_ALLOWED_SCHEMES = frozenset({"agent", "settings", "skill", "mcp", "memory", "handoff"})


class PackageFormatError(ValueError):
    """The manifest or its payload does not conform to package v1."""


def _require_keys(value: Mapping[str, Any], required: set[str], allowed: set[str], where: str) -> None:
    missing = required - set(value)
    extra = set(value) - allowed
    if missing:
        raise PackageFormatError(f"{where} missing required field(s): {', '.join(sorted(missing))}")
    if extra:
        raise PackageFormatError(f"{where} has unknown field(s): {', '.join(sorted(extra))}")


def _is_text(value: Any, *, nonempty: bool = True, limit: int = 1024) -> bool:
    return isinstance(value, str) and (not nonempty or bool(value)) and "\x00" not in value and len(value) <= limit


def _is_logical_source(value: Any) -> bool:
    if (
        not _is_text(value, limit=2048)
        or not value.isascii()
        or not _URI_SAFE.fullmatch(value)
        or re.search(r"%(?![0-9A-Fa-f]{2})", value)
    ):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme not in _ALLOWED_SCHEMES or not _IDENTIFIER.fullmatch(parsed.netloc) or parsed.query or parsed.fragment:
        return False
    if not parsed.path.startswith("/") or parsed.path == "/":
        return False
    segments = [parsed.netloc, *parsed.path[1:].split("/")]
    try:
        decoded = [unquote(segment, errors="strict") for segment in segments]
    except UnicodeDecodeError:
        return False
    return all(
        segment not in {"", ".", ".."} and "/" not in segment and "\\" not in segment and "\x00" not in segment
        for segment in decoded
    )


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_content_id(manifest: Mapping[str, Any]) -> str:
    """Return an identity of portable meaning and bytes, not package instance metadata."""
    by_path = {item["path"]: item for item in manifest.get("objects", [])}
    entries = []
    for entry in manifest.get("entries", []):
        obj = by_path[entry["object_path"]]
        entries.append({
            "logical_source": entry["logical_source"],
            "data_type": entry["data_type"],
            "adapter_id": entry["adapter_id"],
            "adapter_version": entry["adapter_version"],
            "sha256": obj["sha256"],
            "size": obj["size"],
        })
    material = {
        "schema_version": FORMAT_VERSION,
        "scope": {
            "data_types": sorted(manifest["scope"]["data_types"]),
            "agent_ids": sorted(manifest["scope"]["agent_ids"]),
        },
        "adapters": sorted(manifest["adapters"], key=lambda item: (item["id"], item["version"])),
        "entries": sorted(entries, key=lambda item: (item["logical_source"], item["data_type"])),
        "dependencies": sorted(manifest["dependencies"], key=lambda item: (item["id"], item["version"], item["required"])),
    }
    return hashlib.sha256(_canonical(material)).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PackageFormatError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def parse_manifest(data: bytes) -> dict[str, Any]:
    """Parse one UTF-8 manifest while rejecting duplicate keys and non-object roots."""
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise PackageFormatError("Manifest is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise PackageFormatError("Manifest root must be a JSON object")
    return value


def validate_manifest(
    manifest: Mapping[str, Any],
    payloads: Mapping[str, bytes],
    *,
    supported_adapters: Mapping[str, int] | None = None,
    known_content_ids: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Validate format structure and bytes; report adapter/base compatibility separately.

    No mergeability claim is made when a declared parent is absent from
    ``known_content_ids``. Callers must compare content explicitly in that case.
    """
    if not isinstance(manifest, Mapping):
        raise PackageFormatError("Manifest root must be an object")
    _require_keys(
        manifest,
        {"schema_version", "package_id", "content_id", "parent_content_id", "created_at", "scope", "adapters", "objects", "entries", "dependencies", "exclusions"},
        {"schema_version", "package_id", "content_id", "parent_content_id", "created_at", "scope", "adapters", "objects", "entries", "dependencies", "exclusions"},
        "manifest",
    )
    if (
        not isinstance(manifest["schema_version"], int)
        or isinstance(manifest["schema_version"], bool)
        or manifest["schema_version"] != FORMAT_VERSION
    ):
        raise PackageFormatError(f"Unsupported package schema version: {manifest['schema_version']!r}")
    if not isinstance(manifest["package_id"], str) or not _HEX_32.fullmatch(manifest["package_id"]):
        raise PackageFormatError("package_id must be 32 lowercase hexadecimal characters")
    if not isinstance(manifest["content_id"], str) or not _HEX_64.fullmatch(manifest["content_id"]):
        raise PackageFormatError("content_id must be a SHA-256 hex digest")
    parent = manifest["parent_content_id"]
    if parent is not None and (not isinstance(parent, str) or not _HEX_64.fullmatch(parent)):
        raise PackageFormatError("parent_content_id must be null or a SHA-256 hex digest")
    created_at = manifest["created_at"]
    if not _is_text(created_at, limit=64):
        raise PackageFormatError("created_at must be an ISO-8601 timestamp")
    try:
        timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise PackageFormatError("created_at must be an ISO-8601 timestamp") from error
    if timestamp.tzinfo is None:
        raise PackageFormatError("created_at must include a timezone")

    scope = manifest["scope"]
    if not isinstance(scope, Mapping):
        raise PackageFormatError("scope must be an object")
    _require_keys(scope, {"data_types", "agent_ids"}, {"data_types", "agent_ids"}, "scope")
    for field in ("data_types", "agent_ids"):
        values = scope[field]
        if not isinstance(values, list) or any(not _is_text(item, limit=64) for item in values) or len(set(values)) != len(values):
            raise PackageFormatError(f"scope.{field} must be an array of unique strings")
        if field == "data_types" and not set(values) <= DATA_TYPES:
            raise PackageFormatError(f"Unsupported data type in scope: {sorted(set(values) - DATA_TYPES)}")
        if field == "agent_ids" and any(not _IDENTIFIER.fullmatch(item) for item in values):
            raise PackageFormatError("scope.agent_ids contains an invalid portable agent identifier")

    adapters = manifest["adapters"]
    if not isinstance(adapters, list):
        raise PackageFormatError("adapters must be an array")
    adapter_versions: dict[str, int] = {}
    for item in adapters:
        if not isinstance(item, Mapping):
            raise PackageFormatError("Each adapter entry must be an object")
        _require_keys(item, {"id", "version"}, {"id", "version"}, "adapter")
        adapter_id, version = item["id"], item["version"]
        if not isinstance(adapter_id, str) or not _IDENTIFIER.fullmatch(adapter_id):
            raise PackageFormatError("Adapter id is invalid")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise PackageFormatError(f"Adapter {adapter_id} version must be a positive integer")
        if adapter_id in adapter_versions:
            raise PackageFormatError(f"Duplicate adapter id: {adapter_id}")
        adapter_versions[adapter_id] = version

    objects = manifest["objects"]
    if not isinstance(objects, list):
        raise PackageFormatError("objects must be an array")
    object_records: dict[str, Mapping[str, Any]] = {}
    hashes: set[str] = set()
    for item in objects:
        if not isinstance(item, Mapping):
            raise PackageFormatError("Each object entry must be an object")
        _require_keys(item, {"path", "sha256", "size"}, {"path", "sha256", "size"}, "object")
        path, digest, size = item["path"], item["sha256"], item["size"]
        if not isinstance(digest, str) or not _HEX_64.fullmatch(digest):
            raise PackageFormatError("Object sha256 must be a lowercase SHA-256 hex digest")
        if path != f"objects/{digest}.bin":
            raise PackageFormatError(f"Object path must be content-addressed: {path!r}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise PackageFormatError(f"Object size is invalid: {path}")
        if path in object_records or digest in hashes:
            raise PackageFormatError(f"Duplicate object: {path}")
        object_records[path] = item
        hashes.add(digest)
    if set(payloads) != set(object_records):
        missing = sorted(set(object_records) - set(payloads))
        extra = sorted(set(payloads) - set(object_records))
        raise PackageFormatError(f"Package object set mismatch; missing={missing}, extra={extra}")
    for path, item in object_records.items():
        data = payloads[path]
        if not isinstance(data, bytes):
            raise PackageFormatError(f"Package object is not bytes: {path}")
        if len(data) != item["size"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise PackageFormatError(f"Package object integrity check failed: {path}")

    entries = manifest["entries"]
    if not isinstance(entries, list):
        raise PackageFormatError("entries must be an array")
    if not entries:
        raise PackageFormatError("Package must contain at least one portable entry")
    sources: set[str] = set()
    referenced_objects: set[str] = set()
    used_adapters: set[str] = set()
    used_types: set[str] = set()
    unsupported_adapters: set[str] = set()
    for item in entries:
        if not isinstance(item, Mapping):
            raise PackageFormatError("Each file entry must be an object")
        _require_keys(item, {"logical_source", "data_type", "adapter_id", "adapter_version", "object_path"}, {"logical_source", "data_type", "adapter_id", "adapter_version", "object_path"}, "entry")
        source = item["logical_source"]
        if not _is_logical_source(source):
            raise PackageFormatError(f"Entry has an invalid portable logical_source: {source!r}")
        if source in sources:
            raise PackageFormatError(f"Duplicate logical source: {source}")
        sources.add(source)
        data_type = item["data_type"]
        if not isinstance(data_type, str) or data_type not in DATA_TYPES:
            raise PackageFormatError(f"Unsupported data type: {data_type!r}")
        used_types.add(data_type)
        adapter_id, adapter_version = item["adapter_id"], item["adapter_version"]
        if not isinstance(adapter_id, str) or adapter_id not in adapter_versions or adapter_versions[adapter_id] != adapter_version:
            raise PackageFormatError(f"Entry references an undeclared or mismatched adapter: {adapter_id!r}")
        if not isinstance(adapter_version, int) or isinstance(adapter_version, bool):
            raise PackageFormatError(f"Entry adapter version is invalid: {adapter_id!r}")
        used_adapters.add(adapter_id)
        if supported_adapters is None or supported_adapters.get(adapter_id) != adapter_version:
            unsupported_adapters.add(adapter_id)
        object_path = item["object_path"]
        if not isinstance(object_path, str) or object_path not in object_records:
            raise PackageFormatError(f"Entry references an undeclared object: {object_path!r}")
        referenced_objects.add(object_path)
    if set(adapter_versions) != used_adapters:
        raise PackageFormatError("Every declared adapter must be used by at least one entry")
    if set(scope["data_types"]) != used_types:
        raise PackageFormatError("scope.data_types must exactly match the package entries")
    if set(object_records) != referenced_objects:
        raise PackageFormatError("Every declared object must be referenced by an entry")

    dependencies = manifest["dependencies"]
    if not isinstance(dependencies, list):
        raise PackageFormatError("dependencies must be an array")
    dependency_ids: set[str] = set()
    for item in dependencies:
        if not isinstance(item, Mapping):
            raise PackageFormatError("Each dependency must be an object")
        _require_keys(item, {"id", "version", "required"}, {"id", "version", "required"}, "dependency")
        if not isinstance(item["id"], str) or not _IDENTIFIER.fullmatch(item["id"]):
            raise PackageFormatError("Dependency id is invalid")
        if not _is_text(item["version"], limit=64):
            raise PackageFormatError("Dependency version must be a non-empty string")
        if not isinstance(item["required"], bool):
            raise PackageFormatError("Dependency required must be a boolean")
        if item["id"] in dependency_ids:
            raise PackageFormatError(f"Duplicate dependency id: {item['id']}")
        dependency_ids.add(item["id"])

    exclusions = manifest["exclusions"]
    if not isinstance(exclusions, list):
        raise PackageFormatError("exclusions must be an array")
    exclusion_sources: set[str] = set()
    for item in exclusions:
        if not isinstance(item, Mapping):
            raise PackageFormatError("Each exclusion must be an object")
        _require_keys(item, {"logical_source", "category"}, {"logical_source", "category"}, "exclusion")
        if not _is_logical_source(item["logical_source"]):
            raise PackageFormatError("Exclusion logical_source must be portable")
        if not isinstance(item["category"], str) or item["category"] not in EXCLUSION_CATEGORIES:
            raise PackageFormatError(f"Unknown exclusion category: {item['category']!r}")
        if item["logical_source"] in exclusion_sources or item["logical_source"] in sources:
            raise PackageFormatError(f"Duplicate or included exclusion source: {item['logical_source']}")
        exclusion_sources.add(item["logical_source"])

    actual_content_id = compute_content_id(manifest)
    if manifest["content_id"] != actual_content_id:
        raise PackageFormatError("content_id does not match the portable package contents")
    parent_status = "none" if parent is None else "known" if parent in known_content_ids else "unknown"
    return {
        "status": "unsupported_adapter" if unsupported_adapters else "valid",
        "content_id": actual_content_id,
        "entry_count": len(entries),
        "object_count": len(objects),
        "unsupported_adapters": sorted(unsupported_adapters),
        "parent_status": parent_status,
    }
