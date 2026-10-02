import json

from _agent_homes import ReadTracker, SENTINEL
from _machine_fixtures import assert_no_sentinel, assert_tree_unchanged, build_machine_home, snapshot_tree
from sync_core.machine.bundle import BundleWriter
from sync_core.machine.collect_login import add_login_report, login_checklist


def test_login_checklist_uses_names_only_and_does_not_open_secrets(tmp_path, monkeypatch):
    paths = build_machine_home(tmp_path / "home")
    home = paths["home"]
    (home / ".claude" / "settings.json").write_text(json.dumps({"env": {"API_TOKEN": SENTINEL}}), encoding="utf-8")
    (home / ".codex" / "config.toml").write_text(
        '[shell_environment_policy.set]\nSERVICE_KEY = "' + SENTINEL + '"\n', encoding="utf-8")
    ssh = home / ".ssh"
    ssh.mkdir()
    (ssh / "id_ed25519").write_text(SENTINEL, encoding="utf-8")
    before = snapshot_tree(home)
    tracker = ReadTracker(monkeypatch)
    report = login_checklist(home=home, environ={},
                             git_keys=["credential.helper", "credential.https://github.com.username"],
                             mcp_hosts=["accounts.example.org"])
    assert tracker.touched([path for path in paths["protected"]
                            if path != home / ".claude" / "settings.json"]) == []
    assert_tree_unchanged(before, home)
    assert SENTINEL not in report
    assert "API_TOKEN" in report and "SERVICE_KEY" in report
    assert "github.com" in report and "accounts.example.org" in report
    assert "`helper`" not in report
    assert "SSH 私钥" in report and "WorkBuddy" in report
    writer = BundleWriter(tmp_path / "login.zip")
    add_login_report(writer, report)
    writer.finalize()
    assert_no_sentinel(tmp_path / "login.zip")
