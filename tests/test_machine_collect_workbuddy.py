import json

from _agent_homes import ReadTracker, SENTINEL
from _machine_fixtures import assert_no_sentinel, assert_tree_unchanged, build_machine_home, snapshot_tree
from sync_core.machine.bundle import BundleWriter
from sync_core.machine.collect_workbuddy import collect_workbuddy
from sync_core.machine.config import load_config


def test_approved_workbuddy_text_only_and_protected_zero_reads(tmp_path, monkeypatch):
    paths = build_machine_home(tmp_path / "home")
    home = paths["home"]
    config_file = tmp_path / "machine.config.json"
    config_file.write_text(json.dumps({"core_projects": [str(paths["project"])]}), encoding="utf-8")
    config = load_config(config_file, home=home)
    skill = home / ".workbuddy-ai" / "skills" / "office"
    (skill / "binary.bin").write_bytes(b"\x00" + SENTINEL.encode())
    (skill / ".old_migration.json").write_text(SENTINEL, encoding="utf-8")
    (home / ".workbuddy" / "memory" / "private.md").write_text("password: " + "x" * 24, encoding="utf-8")
    for name in ("one", "two"):
        nested = paths["project"] / name / ".workbuddy" / "memory"
        nested.mkdir(parents=True)
        (nested / "note.md").write_text("safe nested note", encoding="utf-8")
    before = snapshot_tree(home)
    tracker = ReadTracker(monkeypatch)
    writer = BundleWriter(tmp_path / "workbuddy.zip")
    result = collect_workbuddy(writer, home=home, config=config, environ={}, os_name="windows")
    manifest = writer.finalize(exclusions=result.exclusions, warnings=result.warnings)
    assert tracker.touched(paths["protected"] + [skill / ".old_migration.json"]) == []
    assert_tree_unchanged(before, home)
    assert_no_sentinel(tmp_path / "workbuddy.zip")
    assert result.verify_sources_unchanged()
    assert all(item["restore"] == "manual" for item in manifest["entries"])
    assert any(item["kind"] == "persona" for item in manifest["entries"])
    assert any(item["project_id"] for item in manifest["entries"])
    assert any(item["reason"] == "non_text" for item in result.exclusions)
    assert any(item["reason"] == "secret_hit" for item in result.exclusions)
    assert not any("AGENTS.md" in item["archive_path"] for item in manifest["entries"])
