from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import zipfile

import pytest

from sync_core.config import SHARED_RULE_TOPICS
from sync_core.package import (
    PackageExportError,
    PortableEntry,
    build_package_manifest,
    collect_portable_config,
    export_archive,
    export_directory,
    check_package,
    validate_manifest,
)
from sync_core.package.policy import CollectionReport


def _store(root: Path) -> None:
    common = root / "common"
    common.mkdir(parents=True)
    for topic in SHARED_RULE_TOPICS:
        body = "" if topic == "security" else f"# {topic}\n"
        (common / f"{topic}.md").write_text(body, encoding="utf-8")


def _load_directory(path: Path) -> tuple[dict, dict[str, bytes]]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    payloads = {item["path"]: (path / item["path"]).read_bytes() for item in manifest["objects"]}
    return manifest, payloads


def test_directory_and_archive_exports_are_self_contained_and_identical(tmp_path):
    store = tmp_path / "store"
    _store(store)
    config = {}
    report = collect_portable_config(config, store)
    directory = tmp_path / "portable-package"
    archive = tmp_path / "portable-package.aiconfig"

    directory_result = export_directory(report, directory, config=config, store_root=store)
    archive_result = export_archive(report, archive, config=config, store_root=store)

    directory_manifest, directory_payloads = _load_directory(directory)
    with zipfile.ZipFile(archive) as zipped:
        archive_manifest = json.loads(zipped.read("manifest.json"))
        archive_payloads = {
            item["path"]: zipped.read(item["path"])
            for item in archive_manifest["objects"]
        }
    assert directory_manifest["content_id"] == archive_manifest["content_id"]
    assert directory_payloads == archive_payloads
    assert validate_manifest(directory_manifest, directory_payloads, supported_adapters={
        item["id"]: item["version"] for item in directory_manifest["adapters"]
    })["status"] == "valid"
    assert directory_result.content_id == archive_result.content_id
    assert (directory / "objects" / "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855.bin").read_bytes() == b""
    assert all(path.name.endswith(".bin") for path in (directory / "objects").iterdir())


def test_manifest_percent_encodes_non_ascii_sources_and_keeps_zero_byte_objects():
    entry = PortableEntry(
        "agent://shared/rules/%E8%A7%84%E5%88%99.md",
        "rule_file",
        "shared_rules",
        1,
        b"",
    )
    report = CollectionReport((entry,), (), (), (), 0)
    manifest, payloads = build_package_manifest(
        report,
        package_id="a" * 32,
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    assert manifest["entries"][0]["logical_source"] == "agent://shared/rules/%E8%A7%84%E5%88%99.md"
    assert manifest["objects"][0]["size"] == 0
    assert next(iter(payloads.values())) == b""
    assert validate_manifest(manifest, payloads, supported_adapters={"shared_rules": 1})["status"] == "valid"


def test_existing_targets_are_not_overwritten_and_source_changes_abort_publication(tmp_path):
    store = tmp_path / "store"
    _store(store)
    config = {}
    report = collect_portable_config(config, store)
    archive = tmp_path / "already-there.aiconfig"
    archive.write_bytes(b"keep me")
    with pytest.raises(PackageExportError, match="already exists"):
        export_archive(report, archive, config=config, store_root=store)
    assert archive.read_bytes() == b"keep me"

    directory = tmp_path / "existing-directory"
    directory.mkdir()
    marker = directory / "keep.txt"
    marker.write_text("keep me", encoding="utf-8")
    with pytest.raises(PackageExportError, match="already exists"):
        export_directory(report, directory, config=config, store_root=store)
    assert marker.read_text(encoding="utf-8") == "keep me"

    (store / "common" / "principles.md").write_text("# changed during export\n", encoding="utf-8")
    with pytest.raises(PackageExportError, match="changed during export"):
        export_directory(report, tmp_path / "stale-output", config=config, store_root=store)
    assert not (tmp_path / "stale-output").exists()
    assert not list(tmp_path.glob(".stale-output.staging-*"))


def test_application_service_previews_then_exports_without_exposing_source_paths(tmp_path):
    from sync_core.application.service import ApplicationService
    from sync_core.package.importer import SUPPORTED_ADAPTERS

    store = tmp_path / "store"
    _store(store)
    (store / "codex").mkdir()
    (store / "codex" / "config.toml").write_text('approval_policy = "on-request"\n', encoding="utf-8")
    codex_root = tmp_path / "codex-home"
    codex_root.mkdir()
    config_path = tmp_path / "device.json"
    config_path.write_text(json.dumps({
        "device": "sender",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory"),
        "config_repo": str(store),
        "codex": str(codex_root),
        "codex_keys": ["approval_policy"],
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "agents": {},
    }), encoding="utf-8")
    destination = tmp_path / "portable.aiconfig"
    service = ApplicationService(config_path)
    selected = ["agent://shared/common/instructions.md"]

    preview = service.package_export(destination=destination, format="archive", selected_sources=selected)

    assert preview.data["can_apply"] is True
    assert preview.data["format"] == "archive"
    assert preview.data["entry_count"] == 1
    assert preview.data["selected_sources"] == selected
    assert str(store) not in json.dumps(preview.data)
    assert not destination.exists()

    result = service.package_export(destination=destination, format="archive", selected_sources=selected, apply=True)

    assert result.data["status"] == "exported"
    assert result.data["written"] is True
    assert result.data["entry_count"] == 1
    checked = check_package(destination, supported_adapters=SUPPORTED_ADAPTERS)
    assert checked.validation["status"] == "valid"
    assert [entry["logical_source"] for entry in checked.manifest["entries"]] == selected
    assert any(item["category"] == "user_excluded" for item in checked.manifest["exclusions"])


def test_application_service_blocks_existing_or_wrong_suffix_export_targets(tmp_path):
    from sync_core.application.service import ApplicationService

    store = tmp_path / "store"
    _store(store)
    config_path = tmp_path / "device.json"
    config_path.write_text(json.dumps({
        "device": "sender",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory"),
        "config_repo": str(store),
    }), encoding="utf-8")
    service = ApplicationService(config_path)
    existing = tmp_path / "existing.aiconfig"
    existing.write_bytes(b"keep")

    occupied = service.package_export(destination=existing, format="archive")
    bad_suffix = service.package_export(destination=tmp_path / "package.zip", format="archive")

    assert occupied.data["can_apply"] is False
    assert "already exists" in (occupied.data["reason"] or "") or "已存在" in (occupied.data["reason"] or "")
    assert bad_suffix.data["can_apply"] is False
    assert "结尾" in (bad_suffix.data["reason"] or "")
    assert existing.read_bytes() == b"keep"
