import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("sync", Path(__file__).parents[1] / "scripts/sync.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def test_three_way_add_change_delete_conflict():
    assert sync.merge({"a.md": b"a"}, {"b.md": b"b"}, {}) == {"a.md": b"a", "b.md": b"b"}
    base = {"a.md": sync.digest(b"old")}
    assert sync.merge({}, {"a.md": b"old"}, base) == {}
    assert sync.merge({"a.md": b"new"}, {"a.md": b"old"}, base) == {"a.md": b"new"}
    with pytest.raises(ValueError, match="Conflicting"):
        sync.merge({"a.md": b"left"}, {"a.md": b"right"}, base)
    with pytest.raises(ValueError):
        sync.merge({}, {"a.md": b"new"}, base)


def test_rules_preserve_existing_and_detect_edits(tmp_path):
    home = tmp_path / "codex"
    home.mkdir()
    target = home / "AGENTS.md"
    target.write_text("My existing instructions\n")
    config = {"state_dir": str(tmp_path / "state"), "codex": str(home)}
    changes = sync.plan(config, "rules")
    assert target.read_text() == "My existing instructions\n"
    assert b"My existing instructions" in changes[target]
    sync.transaction(changes, tmp_path / "backups")
    assert sync.plan(config, "rules") == {}
    target.write_bytes(target.read_bytes().replace(b"Developer Profile", b"Edited Profile"))
    with pytest.raises(ValueError, match="edited"):
        sync.plan(config, "rules")


def test_cli_and_application_service_share_rules_plan(tmp_path, monkeypatch):
    from sync_core.application import plan_local_changes
    from sync_core.config import SHARED_RULE_TOPICS

    source = tmp_path / "source"
    common = source / "common"
    common.mkdir(parents=True)
    for topic in SHARED_RULE_TOPICS:
        (common / f"{topic}.md").write_text(f"# {topic}\n", encoding="utf-8")
    monkeypatch.setattr(sync, "ROOT", source)
    codex = tmp_path / "codex"
    codex.mkdir()
    config = {"state_dir": str(tmp_path / "state"), "codex": str(codex)}

    cli_plan = sync.plan(config, "rules")
    service_plan = plan_local_changes(config, "rules", template_root=source)
    assert service_plan == cli_plan
    assert service_plan.metadata == cli_plan.metadata
    assert service_plan.expected == cli_plan.expected


def test_application_service_memory_apply_creates_the_shared_snapshot_without_cli_config(tmp_path):
    from sync_core.application import ApplicationService

    local_source = tmp_path / "native-memory"
    local_source.mkdir()
    (local_source / "MEMORY.md").write_text("portable note", encoding="utf-8")
    raw = {
        "device": "windows-a",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "shared-memory"),
        "memories": [{"id": "project", "path": str(local_source)}],
    }
    device = tmp_path / "device.json"
    device.write_text(json.dumps(raw), encoding="utf-8")
    service = ApplicationService(device, template_root=tmp_path / "application")

    plan = service.plan(mode="memory")
    result = service.apply_plan(plan)

    assert result["status"] == "applied"
    assert len(result["snapshots"]) == 1
    assert (tmp_path / "shared-memory" / "heads" / "windows-a" / "project.json").is_file()


def test_two_devices_and_deletion(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "ROOT", tmp_path / "config-repo")
    shared = tmp_path / "shared"
    configs = []
    for name in ("a", "b"):
        local = tmp_path / name / "memory"
        local.mkdir(parents=True)
        configs.append({"state_dir": str(tmp_path / name / "state"), "memory_repo": str(shared),
                        "memories": [{"id": "project", "path": str(local)}]})
    file_a = tmp_path / "a/memory/MEMORY.md"
    file_b = tmp_path / "b/memory/MEMORY.md"
    file_a.write_text("remember")
    for config in configs:
        sync.transaction(sync.plan(config, "memory"), tmp_path / "backups")
    assert file_b.read_text() == "remember"
    file_b.unlink()
    for config in reversed(configs):
        sync.transaction(sync.plan(config, "memory"), tmp_path / "backups")
    assert not file_a.exists()
    assert sync.plan(configs[0], "memory") == {}


def test_config_preserves_provider_and_mcp(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text('model_provider = "custom"\n[mcp_servers.test]\ncommand = "example"\n')
    changes = sync.plan({"state_dir": str(tmp_path / "state"), "codex": str(tmp_path),
                         "codex_keys": ["web_search"]}, "config")
    assert b'model_provider = "custom"' in changes[target]
    assert b'[mcp_servers.test]' in changes[target]
    assert b'web_search = "cached"' in changes[target]


def test_rollback(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"old")
    original = sync.write
    def failing(path, data):
        if path == b:
            raise OSError("injected failure")
        original(path, data)
    monkeypatch.setattr(sync, "write", failing)
    with pytest.raises(OSError):
        sync.transaction({a: b"new", b: b"new"}, tmp_path / "backups")
    assert a.read_bytes() == b"old"


def test_secret_and_missing_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "ROOT", tmp_path / "config-repo")
    folder = tmp_path / "memory"
    folder.mkdir()
    (folder / "test.md").write_text("sk-" + "x" * 30)
    with pytest.raises(ValueError, match="secret"):
        sync.files(folder)
    (folder / "test.md").write_text("SERVICE_PASSWORD=" + "test-value")
    with pytest.raises(ValueError, match="secret"):
        sync.files(folder)
    assert sync.files(folder, ["test.md"]) == {}
    with pytest.raises(ValueError, match="missing"):
        sync.plan({"state_dir": str(tmp_path / "state"), "memory_repo": str(tmp_path / "shared"),
                   "memories": [{"id": "test", "path": str(tmp_path / "absent")}]}, "memory")


def test_codex_snapshot_never_overwrites_native_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "ROOT", tmp_path / "config-repo")
    source = tmp_path / "native"
    source.mkdir()
    (source / "summary.md").write_text("native")
    shared = tmp_path / "shared"
    other = shared / "codex/mac/summary.md"
    other.parent.mkdir(parents=True)
    other.write_text("other device")
    config = {"state_dir": str(tmp_path / "state"), "memory_repo": str(shared),
              "device": "windows-a", "codex_memory": str(source)}
    changes = sync.plan(config, "memory")
    assert all(source not in path.parents for path in changes)
    sync.transaction(changes, tmp_path / "backups")
    assert other.read_text() == "other device"
    assert (shared / "codex/windows-a/summary.md").read_text() == "native"
    assert sync.plan(config, "memory") == {}
