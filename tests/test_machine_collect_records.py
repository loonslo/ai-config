from sync_core.machine.collect_records import software_inventory


def test_software_inventory_uses_injected_offline_commands(tmp_path):
    seen = []
    def fake_run(command):
        seen.append(command)
        if command[:2] == ("npm", "ls"):
            return 0, '{"dependencies":{"@openai/codex":{"version":"1.2.3","resolved":"secret"},"bad":{"version":"secret"}}}'
        return 0, "tool version 2.3.4\n"
    root = tmp_path / "claude-code"
    (root / "2.1.281").mkdir(parents=True)
    report = software_inventory(run=fake_run, link_probe=lambda: False, claude_code_dir=root)
    assert report["versions"]["codex_cli"] == "2.3.4"
    assert report["npm_global_packages"] == {"@openai/codex": "1.2.3"}
    assert report["claude_desktop_claude_code_versions"] == ["2.1.281"]
    assert report["codex_desktop_version"] is None
    assert report["symlinks_supported"] is False
    assert ("npm", "ls", "-g", "--depth=0", "--json") in seen
