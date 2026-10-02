from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sync_core.package.format import (
    PackageFormatError,
    compute_content_id,
    parse_manifest,
    validate_manifest,
)


def _manifest(body: bytes = b"Portable rule text.\n") -> tuple[dict, dict[str, bytes]]:
    digest = hashlib.sha256(body).hexdigest()
    path = f"objects/{digest}.bin"
    manifest = {
        "schema_version": 1,
        "package_id": "0123456789abcdef0123456789abcdef",
        "content_id": "0" * 64,
        "parent_content_id": None,
        "created_at": "2026-10-01T00:00:00Z",
        "scope": {"data_types": ["rule_file"], "agent_ids": ["codex"]},
        "adapters": [{"id": "codex_rules", "version": 1}],
        "objects": [{"path": path, "sha256": digest, "size": len(body)}],
        "entries": [{
            "logical_source": "agent://codex/main/AGENTS.md",
            "data_type": "rule_file",
            "adapter_id": "codex_rules",
            "adapter_version": 1,
            "object_path": path,
        }],
        "dependencies": [],
        "exclusions": [],
    }
    manifest["content_id"] = compute_content_id(manifest)
    return manifest, {path: body}


def test_package_v1_example_has_valid_content_and_no_local_identity():
    root = Path(__file__).resolve().parents[1]
    package_dir = root / "docs" / "package-format" / "examples" / "v1-valid"
    manifest = parse_manifest((package_dir / "manifest.json").read_bytes())
    payloads = {
        item["path"]: (package_dir / item["path"]).read_bytes()
        for item in manifest["objects"]
    }

    report = validate_manifest(manifest, payloads, supported_adapters={"codex_rules": 1})

    assert report == {
        "status": "valid",
        "content_id": manifest["content_id"],
        "entry_count": 1,
        "object_count": 1,
        "unsupported_adapters": [],
        "parent_status": "none",
    }
    portable_json = json.dumps(manifest, ensure_ascii=True)
    assert "C:" not in portable_json
    assert "windows-a" not in portable_json


def test_content_identity_ignores_package_id_time_and_parent():
    manifest, payloads = _manifest()
    original = manifest["content_id"]
    manifest["package_id"] = "fedcba9876543210fedcba9876543210"
    manifest["created_at"] = "2026-10-02T12:30:00+00:00"
    manifest["parent_content_id"] = "f" * 64
    assert compute_content_id(manifest) == original

    unknown_base = validate_manifest(manifest, payloads, supported_adapters={"codex_rules": 1})
    known_base = validate_manifest(
        manifest,
        payloads,
        supported_adapters={"codex_rules": 1},
        known_content_ids={"f" * 64},
    )
    assert unknown_base["parent_status"] == "unknown"
    assert known_base["parent_status"] == "known"


def test_package_object_bytes_and_manifest_content_id_are_verified():
    manifest, payloads = _manifest()
    object_path = next(iter(payloads))
    with pytest.raises(PackageFormatError, match="integrity"):
        validate_manifest(manifest, {object_path: b"altered"})

    manifest["content_id"] = "a" * 64
    with pytest.raises(PackageFormatError, match="content_id"):
        validate_manifest(manifest, payloads)


def test_unknown_version_type_adapter_and_missing_base_are_explicit():
    manifest, payloads = _manifest()
    manifest["schema_version"] = 2
    with pytest.raises(PackageFormatError, match="Unsupported package schema version"):
        validate_manifest(manifest, payloads)

    manifest, payloads = _manifest()
    manifest["schema_version"] = 1.0
    with pytest.raises(PackageFormatError, match="Unsupported package schema version"):
        validate_manifest(manifest, payloads)

    manifest, payloads = _manifest()
    manifest["entries"][0]["data_type"] = "unknown_future_type"
    with pytest.raises(PackageFormatError, match="Unsupported data type"):
        validate_manifest(manifest, payloads)

    manifest, payloads = _manifest()
    report = validate_manifest(manifest, payloads, supported_adapters={})
    assert report["status"] == "unsupported_adapter"
    assert report["unsupported_adapters"] == ["codex_rules"]


def test_manifest_rejects_duplicate_keys_and_nonportable_or_duplicate_entries():
    with pytest.raises(PackageFormatError, match="Duplicate JSON object key"):
        parse_manifest(b'{"schema_version":1,"schema_version":1}')

    manifest, payloads = _manifest()
    manifest["entries"][0]["logical_source"] = "agent://codex/../../secret"
    with pytest.raises(PackageFormatError, match="logical_source"):
        validate_manifest(manifest, payloads)

    manifest, payloads = _manifest()
    manifest["entries"].append(dict(manifest["entries"][0]))
    with pytest.raises(PackageFormatError, match="Duplicate logical source"):
        validate_manifest(manifest, payloads)


def test_manifest_rejects_missing_fields_unknown_fields_and_duplicate_objects():
    manifest, payloads = _manifest()
    del manifest["parent_content_id"]
    with pytest.raises(PackageFormatError, match="missing required field"):
        validate_manifest(manifest, payloads)

    manifest, payloads = _manifest()
    manifest["device_path"] = "C:/Users/source"
    with pytest.raises(PackageFormatError, match="unknown field"):
        validate_manifest(manifest, payloads)

    manifest, payloads = _manifest()
    manifest["objects"].append(dict(manifest["objects"][0]))
    with pytest.raises(PackageFormatError, match="Duplicate object"):
        validate_manifest(manifest, payloads)


def test_manifest_rejects_missing_fields_unknown_fields_and_duplicate_objects():
    manifest, payloads = _manifest()
    del manifest["parent_content_id"]
    with pytest.raises(PackageFormatError, match="missing required field"):
        validate_manifest(manifest, payloads)

    manifest, payloads = _manifest()
    manifest["device_path"] = "C:/Users/source"
    with pytest.raises(PackageFormatError, match="unknown field"):
        validate_manifest(manifest, payloads)

    manifest, payloads = _manifest()
    manifest["objects"].append(dict(manifest["objects"][0]))
    with pytest.raises(PackageFormatError, match="Duplicate object"):
        validate_manifest(manifest, payloads)


def test_schema_and_unknown_version_example_are_parseable_and_rejected():
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "schemas" / "package.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == 1
    invalid = parse_manifest((root / "docs" / "package-format" / "examples" / "v1-invalid-unknown-version.json").read_bytes())
    with pytest.raises(PackageFormatError, match="Unsupported package schema version"):
        validate_manifest(invalid, {})
