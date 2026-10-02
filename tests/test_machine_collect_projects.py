import json

from _agent_homes import ReadTracker, SENTINEL
from _machine_fixtures import assert_no_sentinel, assert_tree_unchanged, build_machine_home, snapshot_tree
from sync_core.machine.bundle import BundleWriter, read_bundle
from sync_core.machine.collect_projects import collect_projects, known_folders
from sync_core.machine.config import load_config
from sync_core.machine.paths import norm


def _config(tmp_path, paths):
    source = tmp_path / "machine.config.json"
    source.write_text(json.dumps({"core_projects": [str(paths["project"])]}), encoding="utf-8")
    return load_config(source, home=paths["home"])


def test_project_profile_uses_only_approved_fields_and_counts(tmp_path, monkeypatch):
    paths = build_machine_home(tmp_path / "home")
    home, project = paths["home"], paths["project"]
    registry = home / ".claude.json"
    raw = json.loads(registry.read_text(encoding="utf-8"))
    raw["projects"][str(project).replace("\\", "/")] = {
        "hasTrustDialogAccepted": False, "hasClaudeMdExternalIncludesApproved": True,
        "lastSessionId": SENTINEL,
    }
    registry.write_text(json.dumps(raw), encoding="utf-8")
    nested = project / "sub" / ".claude" / "settings.local.json"
    nested.parent.mkdir(parents=True)
    nested.write_text('{"permissions":{"allow":["Read(/workspace/code)","Edit"]}}', encoding="utf-8")
    desktop = home / "AppData" / "Roaming" / "Claude" / "claude-code-sessions"
    desktop.mkdir(parents=True)
    (desktop / "one.json").write_text(json.dumps({"cwd": str(project), "cliSessionId": SENTINEL}), encoding="utf-8")
    before = snapshot_tree(home)
    tracker = ReadTracker(monkeypatch)
    writer = BundleWriter(tmp_path / "projects.zip")
    result = collect_projects(writer, home=home, config=_config(tmp_path, paths), environ={}, os_name="windows")
    manifest = writer.finalize(projects=result.projects, warnings=result.warnings)
    assert tracker.touched(paths["protected"]) == []
    assert_tree_unchanged(before, home)
    assert_no_sentinel(tmp_path / "projects.zip")
    _, files = read_bundle(tmp_path / "projects.zip")
    assert len(result.projects) == 1
    record = result.projects[0]
    assert record["claude_trust"] == {"hasTrustDialogAccepted": True, "hasClaudeMdExternalIncludesApproved": True}
    assert record["codex_trust"] == "trusted"
    assert (record["claude_session_count"], record["desktop_session_count"], record["codex_thread_count"]) == (1, 1, 1)
    assert (result.local_files, result.local_rules, result.local_absolute_rules) == (2, 3, 1)
    assert norm(project, "windows") in result.known_paths
    assert manifest["projects"] == result.projects
    assert b"oauthAccount" not in b"".join(files.values())
    assert b"lastSessionId" not in b"".join(files.values())
    assert sum(item["kind"] == "trust_fields" for item in manifest["entries"]) == 2


def test_known_folders_is_normalized_and_missing_sqlite_does_not_abort(tmp_path):
    paths = build_machine_home(tmp_path / "home")
    home, project = paths["home"], paths["project"]
    expected = norm(project, "windows")
    assert known_folders(home=home, environ={}, os_name="windows") == [expected]
    (home / ".codex" / "state_5.sqlite").unlink()
    writer = BundleWriter(tmp_path / "missing-db.zip")
    result = collect_projects(writer, home=home, config=_config(tmp_path, paths), environ={}, os_name="windows")
    assert result.projects[0]["codex_thread_count"] == 0
    writer.finalize(projects=result.projects, warnings=result.warnings)
    assert_no_sentinel(tmp_path / "missing-db.zip")


def test_core_folders_remain_distinct_when_they_share_a_git_root(tmp_path):
    paths = build_machine_home(tmp_path / "home")
    extra = paths["project"] / "child"
    extra.mkdir()
    config_file = tmp_path / "two-projects.json"
    config_file.write_text(json.dumps({"core_projects": [str(paths["project"]), str(extra)]}), encoding="utf-8")
    config = load_config(config_file, home=paths["home"])
    writer = BundleWriter(tmp_path / "two-projects.zip")
    result = collect_projects(writer, home=paths["home"], config=config, environ={}, os_name="windows")
    assert len(result.projects) == 2
    assert len({item["project_id"] for item in result.projects}) == 2
    assert len({item["git_root_id"] for item in result.projects}) == 1


def test_local_permissions_with_secret_are_not_copied(tmp_path):
    paths = build_machine_home(tmp_path / "home")
    local = paths["project"] / ".claude" / "settings.local.json"
    local.write_text(json.dumps({"permissions": {"allow": ["password: " + "x" * 24]}}), encoding="utf-8")
    writer = BundleWriter(tmp_path / "secret-permissions.zip")
    result = collect_projects(writer, home=paths["home"], config=_config(tmp_path, paths), environ={}, os_name="windows")
    writer.finalize(projects=result.projects, warnings=result.warnings)
    assert result.local_files == 0
    assert any(item["code"] == "E7203" for item in result.warnings)
    assert_no_sentinel(tmp_path / "secret-permissions.zip")
