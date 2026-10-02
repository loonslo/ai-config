from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from sync_core.config import SHARED_RULE_TOPICS
from sync_core.package import (
    PackageCheckError,
    check_package,
    collect_portable_config,
    export_archive,
    export_directory,
)
import sync_core.package.check as package_check


def _store(root: Path) -> None:
    common = root / "common"
    common.mkdir(parents=True)
    for topic in SHARED_RULE_TOPICS:
        (common / f"{topic}.md").write_text(f"# {topic}\n", encoding="utf-8")


def _export(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = tmp_path / "store"
    _store(store)
    report = collect_portable_config({}, store)
    directory = tmp_path / "package-dir"
    archive = tmp_path / "package.aiconfig"
    export_directory(report, directory, config={}, store_root=store)
    export_archive(report, archive, config={}, store_root=store)
    return directory, archive


def test_checker_reads_directory_and_archive_and_reports_adapter_compatibility(tmp_path):
    directory, archive = _export(tmp_path)
    adapters = {"shared_rules": 1}

    checked_dir = check_package(directory, supported_adapters=adapters)
    checked_zip = check_package(archive, supported_adapters=adapters)

    assert checked_dir.importable and checked_zip.importable
    assert checked_dir.validation["content_id"] == checked_zip.validation["content_id"]
    assert checked_dir.public_summary()["entry_count"] == len(SHARED_RULE_TOPICS)
    assert not check_package(directory, supported_adapters={}).importable
    assert check_package(directory, supported_adapters={}).validation["unsupported_adapters"] == ["shared_rules"]


def test_checker_rejects_zip_traversal_duplicates_and_unregistered_directory_files(tmp_path):
    malicious = tmp_path / "unsafe.aiconfig"
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../outside.txt", b"escape")
    with pytest.raises(PackageCheckError, match="unsafe member path"):
        check_package(malicious)

    directory, _ = _export(tmp_path / "valid")
    (directory / "extra.txt").write_text("unregistered", encoding="utf-8")
    with pytest.raises(PackageCheckError, match="only manifest.json and objects"):
        check_package(directory)


def test_checker_rejects_corrupted_object_and_enforces_per_object_limit(tmp_path, monkeypatch):
    directory, _ = _export(tmp_path)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    first = directory / manifest["objects"][0]["path"]
    original = first.read_bytes()
    first.write_bytes(original + b"tamper")
    with pytest.raises(PackageCheckError, match="size limit|changed while being read|integrity"):
        check_package(directory, supported_adapters={"shared_rules": 1})

    first.write_bytes(original)
    monkeypatch.setattr(package_check, "MAX_OBJECT_BYTES", max(len(original) - 1, 0))
    with pytest.raises(PackageCheckError, match="size limit"):
        check_package(directory, supported_adapters={"shared_rules": 1})


def test_checker_rejects_case_colliding_archive_members(tmp_path):
    archive_path = tmp_path / "collision.aiconfig"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", b"{}")
        archive.writestr("MANIFEST.JSON", b"{}")
    with pytest.raises(PackageCheckError, match="case or Unicode path collision"):
        check_package(archive_path)


def test_checker_reports_deeply_nested_manifest_as_invalid_package(tmp_path):
    archive_path = tmp_path / "deep-manifest.aiconfig"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", b"[" * 1500 + b"0" + b"]" * 1500)
    with pytest.raises(PackageCheckError, match="Manifest"):
        check_package(archive_path)
