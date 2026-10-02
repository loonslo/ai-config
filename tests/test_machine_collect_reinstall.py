import json
import subprocess

from _agent_homes import ReadTracker, SENTINEL
from _machine_fixtures import assert_no_sentinel, assert_tree_unchanged, build_machine_home, snapshot_tree
from sync_core.machine.bundle import BundleWriter, read_bundle
from sync_core.machine.collect_reinstall import add_reinstall_reports, reinstall_inventory


def test_reinstall_report_never_copies_values_or_skill_content(tmp_path, monkeypatch):
    paths = build_machine_home(tmp_path / "home")
    home = paths["home"]
    settings = home / ".claude" / "settings.json"
    settings.write_text(json.dumps({"enabledPlugins": {"review@official": True},
                                    "extraKnownMarketplaces": {"official": {"token": SENTINEL}},
                                    "env": {"PRIVATE": SENTINEL}}), encoding="utf-8")
    plugin_dir = home / ".claude" / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "installed_plugins.json").write_text(json.dumps({"plugins": {
        "review@official": [{"version": "1.2.3", "source": "https://user:pass@example.org/review?token=" + SENTINEL}]
    }}), encoding="utf-8")
    (home / ".codex" / "config.toml").write_text(
        '[mcp_servers.demo]\ncommand = "C:/Tools/node.exe"\nargs = ["' + SENTINEL + '"]\n'
        '[mcp_servers.demo.env]\nAPI_TOKEN = "' + SENTINEL + '"\n'
        '[mcp_servers.remote]\nurl = "https://user:pass@example.org/mcp?token=' + SENTINEL + '"\n'
        '[hooks]\npost = "' + SENTINEL + '"\nnotify = "' + SENTINEL + '"\n', encoding="utf-8")
    skill = home / ".cc-switch" / "skills" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(SENTINEL, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(skill)], check=True)
    subprocess.run(["git", "-C", str(skill), "remote", "add", "origin",
                    "https://user:pass@example.org/review?token=" + SENTINEL], check=True)
    before = snapshot_tree(home)
    tracker = ReadTracker(monkeypatch)
    inventory = reinstall_inventory(home=home, environ={})
    assert tracker.touched([path for path in paths["protected"] if path != settings]) == []
    assert_tree_unchanged(before, home)
    assert len(inventory["cc_switch_skills"]) == 1
    assert inventory["cc_switch_skills"][0]["remote"] == "https://example.org/review"
    assert inventory["codex_mcp_servers"][0]["args_count"] == 1
    assert inventory["codex_mcp_servers"][0]["env_keys"] == ["API_TOKEN"]
    writer = BundleWriter(tmp_path / "reinstall.zip")
    add_reinstall_reports(writer, inventory)
    writer.finalize()
    assert_no_sentinel(tmp_path / "reinstall.zip")
    _, files = read_bundle(tmp_path / "reinstall.zip")
    assert set(files) == {"reports/reinstall.json", "reports/reinstall.md"}
    assert "example.org/mcp" in files["reports/reinstall.json"].decode()
