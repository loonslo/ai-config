"""The agent registry and the platform refactor built on it.

Codex and Claude must behave exactly as before the registry existed (same
bytes, zero changes on an applied device); every other agent is declared under
``agents`` and handled by the same planner and verifier.  All scenarios run in
isolated directories.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sync_core import agents, config_status, config_sync, status
from sync_core.config import DeviceConfig, SHARED_RULE_TOPICS, validate

import scripts.sync as sync_script

from _agent_homes import build_home, device_raw, write_store


# --------------------------------------------------------------------------
# profiles
# --------------------------------------------------------------------------

def test_every_profile_is_complete_and_consistent():
    for profile_id, profile in agents.PROFILES.items():
        assert profile.id == profile_id
        assert profile.name and profile.evidence
        assert profile.level in {agents.LEVEL_DETECT, agents.LEVEL_RULES}
        for instance in profile.instances:
            assert agents.INSTANCE_ID.fullmatch(instance), instance
        if profile.level == agents.LEVEL_DETECT:
            assert profile.rules is None, f"{profile_id} is detect-only and must not declare a write target"
        elif profile_id != agents.GENERIC:
            assert profile.rules is not None, profile_id
            assert profile.locations, profile_id
        if profile.topics is not None:
            assert set(profile.topics) <= set(SHARED_RULE_TOPICS)


def test_instance_ids_resolve_to_their_profiles():
    assert agents.profile_for_instance("workbuddy-ai").id == "workbuddy"
    assert agents.profile_for_instance("trae-cn").id == "trae"
    assert agents.profile_for_instance("codex").id == "codex"
    assert agents.profile_for_instance("generic") is None
    assert agents.profile_for_instance("unknown-agent") is None


def test_protected_name_matching_covers_directories_and_nested_names():
    workbuddy = agents.PROFILES["workbuddy"]
    assert agents.is_sensitive(workbuddy, "keyblob")
    assert agents.is_sensitive(workbuddy, "security/vault.bin")
    assert agents.is_sensitive(workbuddy, "app/connector-keys/k.json")
    assert agents.is_sensitive(agents.PROFILES["codex"], "auth.json")
    assert not agents.is_sensitive(workbuddy, "AGENTS.md")
    assert not agents.is_sensitive(workbuddy, "SOUL.md")


# --------------------------------------------------------------------------
# device declaration
# --------------------------------------------------------------------------

def _raw(tmp_path: Path, **agents_decl) -> dict:
    return device_raw(tmp_path, write_store(tmp_path / "store"), agents=agents_decl or None)


def test_instances_keep_legacy_fields_first_and_agents_sorted(tmp_path):
    store = write_store(tmp_path / "store")
    raw = device_raw(
        tmp_path,
        store,
        legacy={"codex": tmp_path / "codex", "claude": tmp_path / "claude"},
        agents={"workbuddy-ai": {"root": tmp_path / "wb-ai"}, "codebuddy": {"root": tmp_path / "cb"}},
    )
    validate(raw)
    instances = agents.agent_instances(raw)
    assert [item.id for item in instances] == ["codex", "claude", "codebuddy", "workbuddy-ai"]
    assert [item.legacy for item in instances] == [True, True, False, False]
    assert instances[3].profile.id == "workbuddy"
    # WorkBuddy is an office agent: it receives a smaller default topic set.
    assert instances[3].topics == ("instructions", "principles", "security")
    assert instances[0].topics == SHARED_RULE_TOPICS


def test_topics_follow_the_canonical_order_whatever_the_device_lists(tmp_path):
    raw = _raw(tmp_path, codebuddy={"root": tmp_path / "cb", "topics": ["security", "python", "instructions"]})
    validate(raw)
    (instance,) = agents.agent_instances(raw)
    assert instance.topics == ("instructions", "python", "security")


@pytest.mark.parametrize(
    "declaration, message",
    [
        ({"codex": {"root": "C:/x"}}, "top-level"),
        ({"mystery": {"root": "C:/x"}}, "Unknown agent"),
        ({"cursor": {"root": "C:/x"}}, "only be detected"),
        ({"codebuddy": {"root": "C:/x", "extra": 1}}, "unsupported fields"),
        ({"codebuddy": {"root": "C:/x", "topics": ["nonsense"]}}, "unknown topics"),
        ({"codebuddy": {"root": "C:/x", "rules": {"mode": "owned_file", "path": "a.md"}}}, "generic"),
        ({"mine": {"profile": "generic", "root": "C:/x"}}, "declare mode and path"),
        ({"mine": {"profile": "generic", "root": "C:/x", "rules": {"mode": "symlink", "path": "a.md"}}}, "mode must be"),
        ({"mine": {"profile": "generic", "root": "C:/x", "rules": {"mode": "owned_file", "path": "../escape.md"}}}, "inside the agent root"),
        ({"mine": {"profile": "generic", "root": "C:/x", "rules": {"mode": "owned_file", "path": "C:/abs.md"}}}, "inside the agent root"),
        ({"mine": {"profile": "generic", "root": "C:/x", "rules": {"mode": "owned_file", "path": "rules.txt"}}}, ".md"),
        ({"mine": {"profile": "generic", "root": "C:/x", "rules": {"mode": "owned_file", "path": "secrets/a.md"}}}, "protected"),
    ],
)
def test_invalid_agent_declarations_are_rejected(tmp_path, declaration, message):
    raw = device_raw(tmp_path, write_store(tmp_path / "store"))
    raw["agents"] = declaration
    with pytest.raises(ValueError, match=message):
        validate(raw)


def test_a_generic_agent_declares_its_own_entry(tmp_path):
    raw = _raw(tmp_path, mine={"profile": "generic", "root": tmp_path / "mine", "rules": {"mode": "owned_file", "path": "steering/ai-config.md"}})
    validate(raw)
    (instance,) = agents.agent_instances(raw)
    target = agents.rules_target(instance)
    assert target.path == (tmp_path / "mine").resolve() / "steering/ai-config.md"
    assert target.kind == agents.KIND_FILE


# --------------------------------------------------------------------------
# entry resolution
# --------------------------------------------------------------------------

def test_trae_entry_is_probed_and_never_invented(tmp_path):
    root = tmp_path / ".trae-cn"
    root.mkdir()
    raw = _raw(tmp_path, **{"trae-cn": {"root": root}})
    (instance,) = agents.agent_instances(raw)
    assert agents.rules_target(instance) is None
    assert "TRAE" in agents.unresolved_reason(instance)

    (root / "user_rules.md").write_text("mine\n", encoding="utf-8")
    target = agents.rules_target(instance)
    assert (target.path.name, target.mode) == ("user_rules.md", agents.MODE_BLOCK)

    (root / "user_rules.md").unlink()
    (root / "user_rules").mkdir()
    target = agents.rules_target(instance)
    assert (target.path.name, target.mode) == (agents.OWNED_FILE_NAME, agents.MODE_FILE)
    assert agents.unresolved_reason(instance) is None


def test_a_missing_agent_root_is_skipped_but_legacy_roots_keep_old_behaviour(tmp_path):
    raw = _raw(tmp_path, codebuddy={"root": tmp_path / "not-installed"})
    raw["codex"] = str(tmp_path / "codex-not-created")
    targets = agents.managed_targets(raw)
    # Codex has always been written even before its root existed; CodeBuddy is
    # only touched once the agent created its own directory.
    assert [instance.id for instance, _ in targets] == ["codex"]
    (instance,) = [item for item in agents.agent_instances(raw) if item.id == "codebuddy"]
    assert "不会自动创建" in agents.unresolved_reason(instance)


def test_detection_is_read_only_and_finds_every_instance(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("codex", "workbuddy", "workbuddy-ai", "doubao"))
    before = sorted(str(path) for path in home.rglob("*"))
    host = agents.HostEnv.for_home(home, system="windows", environ={}, which=lambda name: None)
    found = {item.instance: item for item in agents.detect_instances(host)}
    assert found["codex"].exists and found["workbuddy"].exists and found["workbuddy-ai"].exists
    assert found["doubao"].exists and found["doubao"].profile.level == agents.LEVEL_DETECT
    assert not found["claude"].exists
    assert sorted(str(path) for path in home.rglob("*")) == before


def test_detection_honours_the_root_override_variable(tmp_path):
    custom = tmp_path / "custom-codex"
    custom.mkdir()
    host = agents.HostEnv.for_home(tmp_path / "home", system="windows", environ={"CODEX_HOME": str(custom)}, which=lambda name: None)
    codex = next(item for item in agents.detect_instances(host) if item.instance == "codex")
    assert codex.root == custom and codex.origin == "环境变量 CODEX_HOME"


# --------------------------------------------------------------------------
# Codex/Claude behaviour is unchanged
# --------------------------------------------------------------------------

def _historical_body(root: Path) -> bytes:
    """The rules block exactly as the pre-registry implementation rendered it."""
    parts = ["<!-- Generated by ai-config; edit common/ in the source repository. -->"]
    for name in ("instructions", "principles", "engineering", "python", "langgraph", "rag", "security"):
        parts.append((root / "common" / f"{name}.md").read_text(encoding="utf-8"))
    return b"<!-- ai-config:begin -->" + b"\n" + ("\n\n".join(parts) + "\n").encode("utf-8") + b"<!-- ai-config:end -->"


def test_codex_and_claude_render_byte_identical_rules(tmp_path):
    store = write_store(tmp_path / "store")
    raw = device_raw(tmp_path, store, legacy={"codex": tmp_path / "codex", "claude": tmp_path / "claude"})
    expected = _historical_body(store)
    for instance in agents.agent_instances(raw):
        assert sync_script._rules_body(raw, instance) == expected
    assert sync_script._rules_body(raw) == expected


def test_an_applied_legacy_device_sees_zero_changes(tmp_path):
    store = write_store(tmp_path / "store")
    (tmp_path / "codex").mkdir()
    (tmp_path / "claude").mkdir()
    (tmp_path / "codex" / "AGENTS.md").write_bytes(b"# mine\n")
    raw = device_raw(tmp_path, store, legacy={"codex": tmp_path / "codex", "claude": tmp_path / "claude"})
    device = DeviceConfig(raw, tmp_path / "device.json")
    report = config_sync.sync(device, apply=True)
    assert report["verified"] is True
    agents_md = (tmp_path / "codex" / "AGENTS.md").read_bytes()
    assert agents_md == b"# mine\n" + b"\n\n" + _historical_body(store) + b"\n"
    plan, _ = config_sync.build_plan(device, apply=True)
    assert len(plan) == 0


# --------------------------------------------------------------------------
# new agents through the same planner and verifier
# --------------------------------------------------------------------------

def _agent_device(tmp_path: Path, **declared) -> DeviceConfig:
    store = write_store(tmp_path / "store")
    raw = device_raw(tmp_path, store, agents=declared)
    validate(raw)
    return DeviceConfig(raw, tmp_path / "device.json")


def test_owned_file_is_created_verified_and_stable(tmp_path):
    root = tmp_path / ".codebuddy"
    root.mkdir()
    device = _agent_device(tmp_path, codebuddy={"root": root})
    report = config_sync.sync(device, apply=True)
    assert report["verified"] is True
    owned = root / "rules" / agents.OWNED_FILE_NAME
    content = owned.read_bytes()
    assert content.startswith(b"<!-- ai-config:begin -->") and content.rstrip().endswith(b"<!-- ai-config:end -->")
    record = next(item for item in config_sync.local_drift(device)["targets"] if item["tool"] == "codebuddy")
    assert (record["target_kind"], record["status"]) == (agents.KIND_FILE, "applied")
    plan, _ = config_sync.build_plan(device, apply=True)
    assert len(plan) == 0


def test_a_foreign_file_is_never_taken_over(tmp_path):
    root = tmp_path / ".codebuddy"
    (root / "rules").mkdir(parents=True)
    foreign = root / "rules" / agents.OWNED_FILE_NAME
    foreign.write_text("written by someone else\n", encoding="utf-8")
    device = _agent_device(tmp_path, codebuddy={"root": root})
    record = next(item for item in config_sync.local_drift(device)["targets"] if item["tool"] == "codebuddy")
    assert record["status"] == "conflict"
    with pytest.raises(config_sync.ConfigSyncError) as info:
        config_sync.sync(device, apply=True)
    assert info.value.exit_code == 4 and "migrate" in str(info.value)
    assert foreign.read_text(encoding="utf-8") == "written by someone else\n"


def test_text_added_next_to_an_owned_block_needs_a_decision(tmp_path):
    root = tmp_path / ".codebuddy"
    root.mkdir()
    device = _agent_device(tmp_path, codebuddy={"root": root})
    config_sync.sync(device, apply=True)
    owned = root / "rules" / agents.OWNED_FILE_NAME
    owned.write_bytes(owned.read_bytes() + b"\nmy extra rule\n")
    record = next(item for item in config_sync.local_drift(device)["targets"] if item["tool"] == "codebuddy")
    assert record["status"] == "local_modified"
    with pytest.raises(config_sync.ConfigSyncError):
        config_sync.sync(device, apply=True)
    # Choosing restore overwrites the edit after a backup, like a shared block.
    config_sync.plan_rules_ownership(device, tool="codebuddy", choice="restore", apply_choice=True, drifting=[record])
    report = config_sync.sync(device, apply=True)
    assert report["verified"] is True
    assert b"my extra rule" not in owned.read_bytes()


def test_workbuddy_block_keeps_the_users_own_text(tmp_path):
    root = tmp_path / ".workbuddy"
    root.mkdir()
    (root / "AGENTS.md").write_text("# 我的工作手册\n", encoding="utf-8")
    device = _agent_device(tmp_path, workbuddy={"root": root})
    config_sync.sync(device, apply=True)
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith("# 我的工作手册\n")
    assert "# instructions" in text and "# security" in text
    # Office defaults leave the coding-only topics out.
    assert "# python" not in text and "# langgraph" not in text


def test_undo_listing_names_the_agent_not_a_guess_from_the_file_name(tmp_path):
    from sync_core.restore import recent_operations

    root = tmp_path / ".workbuddy"
    root.mkdir()
    device = _agent_device(tmp_path, workbuddy={"root": root})
    config_sync.sync(device, apply=True)
    (operation,) = recent_operations(device.state_dir)
    assert operation["tools"] == ["workbuddy"]


def test_receipts_for_new_agents_carry_no_paths(tmp_path):
    root = tmp_path / ".workbuddy"
    root.mkdir()
    device = _agent_device(tmp_path, workbuddy={"root": root})
    config_sync.sync(device, apply=True)
    receipt = status.shared_receipt(config_sync.state_for(device))
    assert status.receipt_is_sensitive_free(receipt)
    assert str(root) not in json.dumps(receipt, ensure_ascii=False)
    assert {item["tool"] for item in receipt["target_digests"]} == {"workbuddy"}
