from __future__ import annotations

import json
from pathlib import Path

import pytest

from sync_core import agents
from sync_core.config import SHARED_RULE_TOPICS
from sync_core.package import PackageImportError, PackageImportService, collect_portable_config, export_archive
from sync_core.restore import restore
from sync_core.transaction import read_bytes, write_file


def _fixture(tmp_path: Path):
    source_store = tmp_path / "source-store"
    (source_store / "common").mkdir(parents=True)
    (source_store / "codex").mkdir()
    for topic in SHARED_RULE_TOPICS:
        (source_store / "common" / f"{topic}.md").write_text(f"# shared {topic}\n", encoding="utf-8")
    (source_store / "codex" / "config.toml").write_text('approval_policy = "on-request"\n', encoding="utf-8")
    source_config = {
        "codex": str(tmp_path / "source-agent" / ".codex"),
        "codex_keys": ["approval_policy"],
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "agents": {},
    }
    report = collect_portable_config(source_config, source_store)
    package_path = tmp_path / "portable.aiconfig"
    export_archive(report, package_path, config=source_config, store_root=source_store)

    home = tmp_path / "receiver-home"
    codex_root = home / ".codex"
    codex_root.mkdir(parents=True)
    receiver_store = tmp_path / "receiver-store"
    (receiver_store / "common").mkdir(parents=True)
    (receiver_store / "codex").mkdir()
    state_root = home / ".ai-sync" / "state"
    config_path = home / ".ai-sync" / "device.json"
    config_path.parent.mkdir(parents=True)
    config = {
        "device": "receiver",
        "state_dir": str(state_root),
        "memory_repo": str(home / "ai-memory"),
        "config_repo": str(receiver_store),
        "codex": str(codex_root),
        "codex_keys": [],
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "agents": {},
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    host = agents.HostEnv.for_home(home, system="windows", environ={}, which=lambda _name: None)
    return package_path, config_path, receiver_store, state_root, codex_root, host


def test_package_import_commits_as_one_undoable_transaction_and_is_idempotent(tmp_path):
    package, config_path, store, state, codex, host = _fixture(tmp_path)
    importer = PackageImportService(config_path, host=host)
    preview = importer.preview(package, store_root=store)
    assert preview.status == "ready"
    assert preview.public_data()["can_apply"] is True

    applied = importer.apply(preview.plan_id)

    assert applied["status"] == "applied"
    assert (store / "common" / "instructions.md").read_bytes().startswith(b"# shared instructions")
    assert (store / "codex" / "config.toml").read_text(encoding="utf-8").strip() == 'approval_policy = "on-request"'
    assert (codex / "config.toml").read_text(encoding="utf-8").strip() == 'approval_policy = "on-request"'
    assert "ai-config:begin" in (codex / "AGENTS.md").read_text(encoding="utf-8")
    saved_config = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved_config["device"] == "receiver"
    assert saved_config["codex_keys"] == ["approval_policy"]

    second = PackageImportService(config_path, host=host).preview(package, store_root=store)
    assert second.status == "unchanged"
    assert second.changed_file_count == 0

    undone = restore(state, operation_id=applied["operation_id"], apply=True)
    assert undone["status"] == "restored"
    assert not (store / "common" / "instructions.md").exists()
    assert not (codex / "config.toml").exists()
    assert not (codex / "AGENTS.md").exists()
    assert json.loads(config_path.read_text(encoding="utf-8"))["codex_keys"] == []
    assert not (state / "package-baseline.aiconfig").exists()


def test_external_change_after_preview_rejects_without_overwriting_it(tmp_path):
    package, config_path, store, _state, _codex, host = _fixture(tmp_path)
    importer = PackageImportService(config_path, host=host)
    preview = importer.preview(package, store_root=store)
    target = store / "common" / "instructions.md"
    target.write_text("# newer local edit\n", encoding="utf-8")

    with pytest.raises(PackageImportError):
        importer.apply(preview.plan_id)

    assert target.read_text(encoding="utf-8").strip() == "# newer local edit"
    assert not (Path(json.loads(config_path.read_text(encoding="utf-8"))["state_dir"]) / "package-baseline.aiconfig").exists()


def test_store_only_import_is_available_when_target_agent_needs_setup(tmp_path):
    package, config_path, store, _state, codex, host = _fixture(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    del config["codex"]
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    importer = PackageImportService(config_path, host=host)
    preview = importer.preview(package, store_root=store, apply_to_agents=False)

    assert preview.status == "ready"
    assert preview.apply_to_agents is False
    result = importer.apply(preview.plan_id)
    assert result["status"] == "applied"
    assert (store / "common" / "instructions.md").exists()
    assert not (codex / "AGENTS.md").exists()
    assert json.loads(config_path.read_text(encoding="utf-8"))["codex_keys"] == []


def test_saved_local_parent_is_reused_for_next_three_way_conflict_preview(tmp_path):
    from sync_core.package import check_package

    package, config_path, store, _state, _codex, host = _fixture(tmp_path)
    old_content_id = check_package(package).validation["content_id"]
    importer = PackageImportService(config_path, host=host)
    first = importer.preview(package, store_root=store)
    importer.apply(first.plan_id)
    (store / "common" / "instructions.md").write_text("# Receiver edit\n", encoding="utf-8")

    next_source = tmp_path / "next-source"
    (next_source / "common").mkdir(parents=True)
    (next_source / "codex").mkdir()
    for topic in SHARED_RULE_TOPICS:
        content = "# Incoming edit\n" if topic == "instructions" else f"# shared {topic}\n"
        (next_source / "common" / f"{topic}.md").write_text(content, encoding="utf-8")
    (next_source / "codex" / "config.toml").write_text('approval_policy = "on-request"\n', encoding="utf-8")
    source_config = {
        "codex": str(tmp_path / "next-agent" / ".codex"),
        "codex_keys": ["approval_policy"],
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "agents": {},
    }
    report = collect_portable_config(source_config, next_source)
    next_package = tmp_path / "next.aiconfig"
    export_archive(
        report,
        next_package,
        config=source_config,
        store_root=next_source,
        parent_content_id=old_content_id,
    )

    second = PackageImportService(config_path, host=host).preview(next_package, store_root=store)
    row = next(
        row for row in second.conflicts.rows
        if row.key == "store:agent://shared/common/instructions.md"
    )
    assert second.conflicts.baseline_status == "verified"
    assert row.status == "conflict" and row.decision is None


def test_mid_transaction_write_failure_restores_all_original_targets(tmp_path, monkeypatch):
    package, config_path, store, state, codex, host = _fixture(tmp_path)
    importer = PackageImportService(config_path, host=host)
    preview = importer.preview(package, store_root=store)
    before_config = config_path.read_bytes()
    before_instructions = (store / "common" / "instructions.md").read_bytes() if (store / "common" / "instructions.md").exists() else None
    import sync_core.package.importer as importer_module

    real_write = importer_module.write_file
    write_count = 0

    def fail_after_second_write(path: Path, content: bytes | None) -> None:
        nonlocal write_count
        write_count += 1
        real_write(path, content)
        if write_count == 2:
            raise OSError("injected disk failure")

    monkeypatch.setattr(importer_module, "write_file", fail_after_second_write)
    with pytest.raises(PackageImportError):
        importer.apply(preview.plan_id)

    assert config_path.read_bytes() == before_config
    assert read_bytes(store / "common" / "instructions.md") == before_instructions
    assert read_bytes(codex / "config.toml") is None
    assert read_bytes(codex / "AGENTS.md") is None
    assert read_bytes(state / "package-baseline.aiconfig") is None


def test_desktop_protocol_rechecks_then_applies_package_preview(tmp_path):
    from sync_core.application.protocol import ApplicationProtocol

    package, config_path, store, _state, _codex, _host = _fixture(tmp_path)
    protocol = ApplicationProtocol(config_path)
    preview = protocol.handle({
        "protocol_version": 1,
        "request_id": "package-preview",
        "type": "preview",
        "operation": "package_import",
        "params": {"package_path": str(package)},
    })
    assert preview["status"] == "preview"
    assert preview["can_apply"] is True
    assert "plan_id" in preview

    applied = protocol.handle({
        "protocol_version": 1,
        "request_id": "package-apply",
        "type": "apply",
        "plan_id": preview["plan_id"],
    })

    assert applied["status"] == "applied"
    assert applied["result"]["status"] == "applied"
    assert (store / "common" / "instructions.md").exists()


def test_package_import_preview_exposes_agent_choices_without_local_roots(tmp_path, monkeypatch):
    from sync_core.package import mapping

    package, config_path, store, _state, _codex, host = _fixture(tmp_path)
    roots = (tmp_path / "first-agent-root", tmp_path / "second-agent-root")
    candidates = tuple(
        mapping.AgentCandidate(f"codex-{index}", "codex", root, True, False, "detected")
        for index, root in enumerate(roots, start=1)
    )
    monkeypatch.setattr(mapping, "_candidate_instances", lambda _raw, _profile, _host: candidates)

    preview = PackageImportService(config_path, host=host).preview(package, store_root=store)
    public = preview.public_data()

    assert preview.status == "needs_selection"
    assert len(public["agent_selections"]) == 1
    assert {item["instance_id"] for item in public["agent_selections"][0]["candidates"]} == {"codex-1", "codex-2"}
    assert all("root" not in item for item in public["agent_selections"][0]["candidates"])
    assert all(str(root) not in json.dumps(public) for root in roots)
