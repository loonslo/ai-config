from __future__ import annotations

from pathlib import Path

from sync_core import agents
from sync_core.config import SHARED_RULE_TOPICS
from sync_core.package import (
    check_package,
    collect_portable_config,
    export_archive,
    plan_package_mappings,
)


ADAPTERS = {
    "shared_rules": 1,
    "codex_settings": 1,
    "agent_declaration": 1,
}


def _store(root: Path, *, codex_setting: bool = True) -> None:
    common = root / "common"
    common.mkdir(parents=True)
    for topic in SHARED_RULE_TOPICS:
        (common / f"{topic}.md").write_text(f"# {topic}\n", encoding="utf-8")
    if codex_setting:
        (root / "codex").mkdir()
        (root / "codex" / "config.toml").write_text('approval_policy = "on-request"\n', encoding="utf-8")


def _package(tmp_path: Path, *, include_declaration: bool = True, codex_setting: bool = True):
    source_store = tmp_path / "source-store"
    _store(source_store, codex_setting=codex_setting)
    source_root = tmp_path / "source-agent"
    source_config = {
        "codex": str(source_root / ".codex"),
        "codex_keys": ["approval_policy"] if codex_setting else [],
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "agents": {},
    }
    if include_declaration:
        source_config["agents"]["workbuddy-custom"] = {
            "profile": "workbuddy",
            "root": str(source_root / ".workbuddy"),
            "topics": ["instructions", "security"],
        }
    report = collect_portable_config(source_config, source_store)
    assert not report.unsupported and not report.review_required
    output = tmp_path / "portable.aiconfig"
    result = export_archive(report, output, config=source_config, store_root=source_store)
    package = check_package(output, supported_adapters=ADAPTERS)
    assert package.validation["content_id"] == result.content_id
    return package


def _target_config(home: Path) -> dict:
    return {
        "device": "receiver-device",
        "state_dir": str(home / ".ai-sync" / "state"),
        "memory_repo": str(home / "ai-memory"),
        "codex": str(home / ".codex"),
        "codex_keys": [],
        "codex_overrides": {"web_search": False},
        "claude_keys": [],
        "claude_overrides": {},
        "agents": {},
    }


def test_mapping_uses_receiver_paths_and_preserves_device_identity(tmp_path):
    package = _package(tmp_path)
    home = tmp_path / "receiver-home"
    (home / ".codex").mkdir(parents=True)
    (home / ".workbuddy").mkdir(parents=True)
    store = tmp_path / "receiver-store"
    store.mkdir()
    receiver = _target_config(home)
    host = agents.HostEnv.for_home(home, system="windows", environ={}, which=lambda _name: None)

    plan = plan_package_mappings(
        package,
        store_root=store,
        device_config=receiver,
        host=host,
    )

    assert plan.status == "ready"
    assert plan.can_save_to_store and plan.can_apply_to_agents
    setting = next(item for item in plan.items if item.logical_source == "settings://codex/main/approval_policy")
    assert setting.target_path == home / ".codex" / "config.toml"
    rule = next(item for item in plan.items if item.logical_source.endswith("/common/instructions.md"))
    assert rule.storage_path == store / "common" / "instructions.md"
    proposal = plan.proposed_device_config
    assert proposal is not None
    assert proposal["device"] == "receiver-device"
    assert proposal["memory_repo"] == receiver["memory_repo"]
    assert proposal["codex_keys"] == ["approval_policy"]
    assert proposal["codex_overrides"] == {"web_search": False}
    assert proposal["agents"]["workbuddy"]["root"] == str(home / ".workbuddy")
    assert receiver["codex_keys"] == []
    assert receiver["agents"] == {}
    public = str(plan.public_data())
    assert "workbuddy-custom" not in public
    assert receiver["device"] not in public
    assert receiver["memory_repo"] not in public
    assert "local-choice" not in public


def test_multiple_agent_candidates_require_explicit_instance_selection(tmp_path):
    package = _package(tmp_path, include_declaration=True, codex_setting=False)
    home = tmp_path / "receiver-home"
    (home / ".workbuddy").mkdir(parents=True)
    (home / ".workbuddy-ai").mkdir(parents=True)
    store = tmp_path / "receiver-store"
    store.mkdir()
    receiver = _target_config(home)
    host = agents.HostEnv.for_home(home, system="windows", environ={}, which=lambda _name: None)

    preview = plan_package_mappings(package, store_root=store, device_config=receiver, host=host)
    declaration = next(item for item in preview.items if item.logical_source == "agent://shared/declarations.json")
    assert preview.status == "needs_selection"
    assert not preview.can_apply_to_agents
    assert {candidate.instance_id for candidate in declaration.candidates} == {"workbuddy", "workbuddy-ai"}

    selected = plan_package_mappings(
        package,
        store_root=store,
        device_config=receiver,
        host=host,
        selections={"workbuddy:1": "workbuddy-ai"},
    )
    assert selected.status == "ready"
    assert selected.proposed_device_config["agents"]["workbuddy-ai"]["root"] == str(home / ".workbuddy-ai")

    forged = plan_package_mappings(
        package,
        store_root=store,
        device_config=receiver,
        host=host,
        selections={"workbuddy:1": str(tmp_path / "attacker-controlled")},
    )
    assert forged.status == "needs_selection"
    assert not forged.can_apply_to_agents


def test_uninstalled_agent_is_saved_as_pending_and_local_overrides_are_preserved(tmp_path):
    package = _package(tmp_path, include_declaration=False, codex_setting=True)
    home = tmp_path / "receiver-home"
    home.mkdir()
    store = tmp_path / "receiver-store"
    store.mkdir()
    host = agents.HostEnv.for_home(home, system="windows", environ={}, which=lambda _name: None)
    config = _target_config(home)
    config["codex"] = str(home / ".codex")

    pending = plan_package_mappings(package, store_root=store, device_config=config, host=host)
    setting = next(item for item in pending.items if item.logical_source == "settings://codex/main/approval_policy")
    assert pending.status == "partial"
    assert pending.can_save_to_store
    assert not pending.can_apply_to_agents
    assert setting.status == "not_installed"

    (home / ".codex").mkdir()
    config["codex"] = str(home / ".codex")
    config["codex_overrides"] = {"approval_policy": "local-choice"}
    conflicted = plan_package_mappings(package, store_root=store, device_config=config, host=host)
    assert conflicted.status == "blocked"
    assert not conflicted.can_apply_to_agents
    assert conflicted.proposed_device_config["device"] == "receiver-device"
    assert conflicted.proposed_device_config["codex_overrides"]["approval_policy"] == "local-choice"
    assert "local-choice" not in str(conflicted.public_data())
