from datetime import datetime, timezone
import json

import pytest

from _agent_homes import ReadTracker
from _machine_fixtures import assert_no_sentinel, assert_tree_unchanged, build_machine_home, snapshot_tree
from sync_core.machine.backup import apply_backup, prepare_backup
from sync_core.machine.bundle import BundleError, read_bundle
from sync_core.machine.config import load_config


SOFTWARE = {"versions": {"python": "3.14.0"}, "unverified": []}
NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


def _setup(tmp_path):
    paths = build_machine_home(tmp_path / "home")
    config_file = tmp_path / "machine.config.json"
    config_file.write_text(json.dumps({"core_projects": [str(paths["project"])]}), encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    return paths, load_config(config_file, home=paths["home"]), output


def test_backup_preview_zero_writes_apply_valid_and_stable_content(tmp_path):
    paths, config, output = _setup(tmp_path)
    before = snapshot_tree(paths["home"])
    plans = [prepare_backup(home=paths["home"], config=config, out=output, name=name,
                            environ={}, os_name="windows", now=NOW, software=SOFTWARE, git_keys=[])
             for name in ("one", "two")]
    assert list(output.iterdir()) == []
    assert plans[0].preview()["content_id"] == plans[1].preview()["content_id"]
    report = apply_backup(plans[0])
    assert report["mode"] == "applied" and len(report["sha256"]) == 64
    assert_no_sentinel(plans[0].writer.destination)
    manifest, files = read_bundle(plans[0].writer.destination)
    assert {"reports/projects.json", "reports/software.json", "reports/reinstall.json",
            "reports/reinstall.md", "reports/login-checklist.md", "reports/summary.md"} <= set(files)
    assert manifest["projects"]
    assert_tree_unchanged(before, paths["home"])
    assert all(plan.verify_sources_unchanged() for plan in plans)


def test_backup_agent_filter_does_not_read_other_assistants(tmp_path, monkeypatch):
    paths, config, output = _setup(tmp_path)
    tracker = ReadTracker(monkeypatch)
    plan = prepare_backup(home=paths["home"], config=config, out=output,
                          agents=frozenset({"codex"}), environ={}, os_name="windows",
                          now=NOW, software=SOFTWARE, git_keys=[])
    assert all(item["agent"] in {"codex", "report"} for item in plan.writer.entries)
    assert tracker.touched([paths["home"] / ".claude.json",
                            paths["home"] / ".claude" / "settings.json",
                            paths["home"] / ".workbuddy" / "SOUL.md",
                            paths["home"] / ".workbuddy" / "settings.json"]) == []
    apply_backup(plan)
    assert_no_sentinel(plan.writer.destination)


def test_backup_rejects_output_inside_sources_and_changes_after_preview(tmp_path):
    paths, config, output = _setup(tmp_path)
    for forbidden in (paths["project"], paths["home"] / ".codex"):
        with pytest.raises(ValueError, match="inside"):
            prepare_backup(home=paths["home"], config=config, out=forbidden, environ={}, software=SOFTWARE)
    plan = prepare_backup(home=paths["home"], config=config, out=output, environ={},
                          now=NOW, software=SOFTWARE, git_keys=[])
    (paths["home"] / ".codex" / "AGENTS.md").write_text("changed", encoding="utf-8")
    with pytest.raises(BundleError, match="changed"):
        apply_backup(plan)
    assert list(output.iterdir()) == []
