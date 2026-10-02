import json

from _agent_homes import ReadTracker
from _machine_fixtures import assert_no_sentinel, assert_tree_unchanged, build_machine_home, snapshot_tree
from sync_core.machine.bundle import BundleWriter, read_bundle
from sync_core.machine.collect_tier1 import collect_tier1
from sync_core.machine.config import load_config


def _config(tmp_path, paths):
    file = tmp_path / "machine.config.json"
    file.write_text(json.dumps({"core_projects": [str(paths["project"])]}), encoding="utf-8")
    return load_config(file, home=paths["home"])


def test_tier1_collection_keeps_sources_and_protected_files_untouched(tmp_path, monkeypatch):
    paths = build_machine_home(tmp_path / "home")
    config = _config(tmp_path, paths)
    before = snapshot_tree(paths["home"])
    tracker = ReadTracker(monkeypatch)
    writer = BundleWriter(tmp_path / "one.zip")
    result = collect_tier1(writer, home=paths["home"], config=config, environ={}, os_name="windows")
    manifest = writer.finalize(exclusions=result.exclusions, warnings=result.warnings)
    assert result.verify_sources_unchanged()
    never_read = [path for path in paths["protected"] if path != paths["home"] / ".claude" / "settings.json"]
    assert tracker.touched([*never_read, paths["home"] / ".claude.json", paths["home"] / ".codex" / "state_5.sqlite"]) == []
    assert_tree_unchanged(before, paths["home"])
    assert_no_sentinel(tmp_path / "one.zip")
    checked, files = read_bundle(tmp_path / "one.zip")
    assert checked["content_id"] == manifest["content_id"]
    assert any(entry["kind"] == "memory" for entry in manifest["entries"])
    assert any(entry["kind"] == "rules" for entry in manifest["entries"])
    assert any(entry["kind"] == "settings_fields" for entry in manifest["entries"])
    assert any(item["reason"] == "non_text" for item in result.exclusions)
    codex_fields = next(entry for entry in manifest["entries"] if entry["agent"] == "codex" and entry["kind"] == "settings_fields")
    assert codex_fields["fields"] == ["model_reasoning_effort"]
    assert codex_fields["confirm_fields"] == []
    assert "shell_environment_policy" not in files[codex_fields["archive_path"]].decode()
    assert all("workbuddy" not in path for path in files)
    assert all(".system" not in path for path in files)


def test_tier1_content_id_stable_and_agent_filter(tmp_path):
    paths = build_machine_home(tmp_path / "home")
    config = _config(tmp_path, paths)
    ids = []
    for name in ("first.zip", "second.zip"):
        writer = BundleWriter(tmp_path / name)
        result = collect_tier1(writer, home=paths["home"], config=config, environ={}, os_name="windows")
        ids.append(writer.finalize(exclusions=result.exclusions)["content_id"])
    assert ids[0] == ids[1]
    writer = BundleWriter(tmp_path / "codex.zip")
    collect_tier1(writer, home=paths["home"], config=config, environ={}, os_name="windows", agents=frozenset({"codex"}))
    manifest = writer.finalize()
    assert all(entry["agent"] == "codex" for entry in manifest["entries"])


def test_source_verification_detects_later_edits(tmp_path):
    paths = build_machine_home(tmp_path / "home")
    writer = BundleWriter(tmp_path / "not-written.zip")
    result = collect_tier1(writer, home=paths["home"], config=_config(tmp_path, paths), environ={}, os_name="windows")
    assert result.verify_sources_unchanged()
    (paths["home"] / ".codex" / "AGENTS.md").write_text("changed", encoding="utf-8")
    assert not result.verify_sources_unchanged()


def test_secret_hit_memory_is_excluded_without_reading_link_target(tmp_path, monkeypatch):
    paths = build_machine_home(tmp_path / "home")
    config = _config(tmp_path, paths)
    memory = next((paths["home"] / ".claude" / "projects").glob("*/memory"))
    secret = memory / "private.md"
    secret.write_text("password: " + "x" * 24, encoding="utf-8")
    linked = memory / "linked.md"
    try:
        linked.symlink_to(paths["home"] / ".claude" / ".credentials.json")
    except (OSError, NotImplementedError):
        pass
    tracker = ReadTracker(monkeypatch)
    writer = BundleWriter(tmp_path / "safe.zip")
    result = collect_tier1(writer, home=paths["home"], config=config, environ={}, os_name="windows")
    writer.finalize(exclusions=result.exclusions)
    assert any(item["reason"] == "secret_hit" for item in result.exclusions)
    assert all("private.md" not in entry["archive_path"] for entry in writer.entries)
    assert tracker.touched([paths["home"] / ".claude" / ".credentials.json"]) == []
    assert_no_sentinel(tmp_path / "safe.zip")
