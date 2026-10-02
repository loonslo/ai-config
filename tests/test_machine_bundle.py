from __future__ import annotations

import json
from pathlib import Path
import stat
import warnings
import zipfile

import pytest

from sync_core.machine import bundle


def _valid(tmp_path: Path) -> tuple[Path, dict]:
    path = tmp_path / "original.zip"
    writer = bundle.BundleWriter(path, source={"os": "windows"})
    writer.add_file("files/claude/main/记忆.md", "内容\n".encode(), agent="claude", instance="main",
                    kind="memory", logical_path="claude:main/记忆.md")
    writer.add_report("summary.md", "备份完成。")
    return path, writer.finalize()


def _rewrite(path: Path, manifest: dict | str, files: dict[str, bytes], *, compression: int = zipfile.ZIP_DEFLATED,
             special: dict[str, zipfile.ZipInfo] | None = None) -> Path:
    target = path.with_name(path.stem + "-altered.zip")
    raw = manifest if isinstance(manifest, str) else json.dumps(manifest, ensure_ascii=False)
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", raw, compress_type=compression)
        for name, data in files.items():
            archive.writestr((special or {}).get(name, name), data, compress_type=compression)
    return target


def _contents(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist() if name != "manifest.json"}


def test_roundtrip_unicode_and_stable_content_identity(tmp_path):
    first, manifest = _valid(tmp_path)
    checked, files = bundle.read_bundle(first)
    assert checked["content_id"] == manifest["content_id"]
    assert files["files/claude/main/记忆.md"] == "内容\n".encode()
    other = tmp_path / "second.zip"
    writer = bundle.BundleWriter(other)
    writer.add_file("files/claude/main/记忆.md", "内容\n".encode(), agent="claude", instance="main",
                    kind="memory", logical_path="claude:main/记忆.md")
    writer.add_report("summary.md", "备份完成。")
    assert writer.finalize()["content_id"] == manifest["content_id"]
    with pytest.raises(bundle.BundleError):
        writer.finalize()
    assert not other.with_name(other.name + ".partial").exists()


@pytest.mark.parametrize("name", ["/absolute", "../escape", "files/../escape", "C:/drive", "bad\x01name", "x" * 241, "bad\\slash"])
def test_rejects_unsafe_member_names(tmp_path, name):
    source, manifest = _valid(tmp_path)
    files = _contents(source)
    files[name] = b"x"
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(_rewrite(source, manifest, files))


def test_rejects_null_member_name(tmp_path):
    source, manifest = _valid(tmp_path)
    files = _contents(source)
    files["badname"] = b"x"
    archive = _rewrite(source, manifest, files)
    archive.write_bytes(archive.read_bytes().replace(b"badname", b"bad\0ame"))
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(archive)


def test_rejects_case_and_nfc_duplicate_members(tmp_path):
    source, manifest = _valid(tmp_path)
    for names in (("files/one", "files/ONE"), ("files/é", "files/e\u0301")):
        files = _contents(source)
        files.update({name: b"x" for name in names})
        with pytest.raises(bundle.BundleError):
            bundle.validate_bundle(_rewrite(source, manifest, files))


def test_rejects_symbolic_link_and_unsupported_compression(tmp_path):
    source, manifest = _valid(tmp_path)
    files = _contents(source)
    target = next(iter(files))
    link = zipfile.ZipInfo(target)
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(_rewrite(source, manifest, files, special={target: link}))
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(_rewrite(source, manifest, files, compression=zipfile.ZIP_BZIP2))


def test_rejects_member_count_and_size_limits(tmp_path, monkeypatch):
    source, manifest = _valid(tmp_path)
    monkeypatch.setattr(bundle, "MAX_MEMBERS", 2)
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(source)
    monkeypatch.setattr(bundle, "MAX_MEMBERS", 20_000)
    monkeypatch.setattr(bundle, "MAX_FILE_BYTES", 5)
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(source)
    monkeypatch.setattr(bundle, "MAX_FILE_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(bundle, "MAX_TOTAL_BYTES", 20)
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(source)
    monkeypatch.setattr(bundle, "MAX_TOTAL_BYTES", 512 * 1024 * 1024)
    monkeypatch.setattr(bundle, "MAX_MANIFEST_BYTES", 30)
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(source)


def test_rejects_abnormal_compression_ratio(tmp_path):
    source, manifest = _valid(tmp_path)
    files = _contents(source)
    files["files/bomb"] = b"a" * 2_000_000
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(_rewrite(source, manifest, files))


@pytest.mark.parametrize("mutate", [
    lambda m: m.update(schema_version=2),
    lambda m: m.update(unknown=True),
    lambda m: m["entries"][0].update(sha256="0" * 64),
    lambda m: m["entries"][0].update(size=0),
    lambda m: m["entries"].append({**m["entries"][0], "id": "extra", "archive_path": "files/missing"}),
    lambda m: m.update(content_id="0" * 64),
])
def test_rejects_invalid_manifest_claims(tmp_path, mutate):
    source, manifest = _valid(tmp_path)
    mutate(manifest)
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(_rewrite(source, manifest, _contents(source)))


@pytest.mark.parametrize("raw", ['{"format":1,"format":2}', '{"number":NaN}', '{"number":Infinity}', '{'])
def test_rejects_invalid_manifest_json(tmp_path, raw):
    source, _ = _valid(tmp_path)
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(_rewrite(source, raw, _contents(source)))


def test_rejects_extra_and_missing_files(tmp_path):
    source, manifest = _valid(tmp_path)
    files = _contents(source)
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(_rewrite(source, manifest, {**files, "files/extra": b"x"}))
    files.pop(next(iter(files)))
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(_rewrite(source, manifest, files))


def test_rejects_truncated_central_directory_and_duplicate_zip_names(tmp_path):
    source, manifest = _valid(tmp_path)
    damaged = tmp_path / "truncated.zip"
    damaged.write_bytes(source.read_bytes()[:-20])
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(damaged)
    duplicate = tmp_path / "duplicate.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("files/duplicate", b"a")
            archive.writestr("files/duplicate", b"a")
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(duplicate)
