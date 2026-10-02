from __future__ import annotations

from pathlib import Path

from sync_core import agents
from sync_core.config import SHARED_RULE_TOPICS
from sync_core.package import (
    check_package,
    collect_portable_config,
    export_archive,
    inspect_package_targets,
    plan_package_conflicts,
    plan_package_mappings,
)


ADAPTERS = {"shared_rules": 1, "codex_settings": 1, "agent_declaration": 1}


def _make_package(tmp_path: Path, name: str, *, instruction: str, parent: str | None = None):
    root = tmp_path / f"source-{name}"
    (root / "common").mkdir(parents=True)
    for topic in SHARED_RULE_TOPICS:
        text = instruction if topic == "instructions" else f"# {topic}\n"
        (root / "common" / f"{topic}.md").write_text(text, encoding="utf-8")
    (root / "codex").mkdir()
    (root / "codex" / "config.toml").write_text('approval_policy = "on-request"\n', encoding="utf-8")
    config = {
        "codex": str(tmp_path / f"source-agent-{name}" / ".codex"),
        "codex_keys": ["approval_policy"],
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "agents": {},
    }
    report = collect_portable_config(config, root)
    output = tmp_path / f"{name}.aiconfig"
    result = export_archive(report, output, config=config, store_root=root, parent_content_id=parent)
    return check_package(output, supported_adapters=ADAPTERS), result


def _receiver(tmp_path: Path):
    home = tmp_path / "receiver-home"
    codex = home / ".codex"
    codex.mkdir(parents=True)
    store = tmp_path / "receiver-store"
    (store / "common").mkdir(parents=True)
    (store / "codex").mkdir()
    config = {
        "device": "receiver-device",
        "state_dir": str(home / ".ai-sync" / "state"),
        "memory_repo": str(home / "ai-memory"),
        "codex": str(codex),
        "codex_keys": [],
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "agents": {},
    }
    host = agents.HostEnv.for_home(home, system="windows", environ={}, which=lambda _name: None)
    return home, store, config, host


def _inspect(package, store: Path, config: dict, host: agents.HostEnv):
    mapping = plan_package_mappings(package, store_root=store, device_config=config, host=host)
    assert mapping.status == "ready"
    return mapping, inspect_package_targets(package, mapping, store_root=store)


def test_conflicts_require_choice_without_verified_baseline_and_never_create_deletions(tmp_path):
    package, _ = _make_package(tmp_path, "incoming", instruction="# Incoming\n", parent="a" * 64)
    _, store, config, host = _receiver(tmp_path)
    (store / "common" / "instructions.md").write_text("# Local edit\n", encoding="utf-8")
    mapping, snapshot = _inspect(package, store, config, host)

    plan = plan_package_conflicts(package, mapping, snapshot)

    row = next(row for row in plan.rows if row.key == "store:agent://shared/common/instructions.md")
    assert plan.baseline_status == "unknown"
    assert row.status == "needs_choice" and row.decision is None
    assert row.choices == ("keep_local", "use_package", "manual_merge")
    assert not plan.can_update_store
    assert not any("delete" in row.key for row in plan.rows)
    assert "# Incoming" not in str(plan.public_data())

    chosen = plan_package_conflicts(
        package, mapping, snapshot,
        decisions={row.key: "use_package"},
    )
    assert chosen.can_update_store
    assert chosen.resolved_store_values[row.logical_source].replace(b"\r\n", b"\n") == b"# Incoming\n"


def test_verified_parent_enables_per_source_three_way_comparison(tmp_path):
    base, base_result = _make_package(tmp_path, "base", instruction="# Base\n")
    incoming, _ = _make_package(
        tmp_path, "incoming", instruction="# Incoming\n", parent=base_result.content_id
    )
    _, store, config, host = _receiver(tmp_path)
    for topic in SHARED_RULE_TOPICS:
        value = "# Base\n" if topic == "instructions" else f"# {topic}\n"
        (store / "common" / f"{topic}.md").write_text(value, encoding="utf-8")
    (store / "codex" / "config.toml").write_text('approval_policy = "on-request"\n', encoding="utf-8")
    mapping, snapshot = _inspect(incoming, store, config, host)

    plan = plan_package_conflicts(incoming, mapping, snapshot, base_package=base)

    row = next(row for row in plan.rows if row.key == "store:agent://shared/common/instructions.md")
    assert plan.baseline_status == "verified"
    assert row.status == "incoming_only" and row.decision == "use_package"
    assert plan.can_update_store


def test_parent_mismatch_is_not_accepted_as_a_baseline(tmp_path):
    base, _ = _make_package(tmp_path, "base", instruction="# Base\n")
    incoming, _ = _make_package(
        tmp_path, "incoming", instruction="# Incoming\n", parent="f" * 64
    )
    _, store, config, host = _receiver(tmp_path)
    (store / "common" / "instructions.md").write_text("# Local\n", encoding="utf-8")
    mapping, snapshot = _inspect(incoming, store, config, host)

    plan = plan_package_conflicts(incoming, mapping, snapshot, base_package=base)

    row = next(row for row in plan.rows if row.key == "store:agent://shared/common/instructions.md")
    assert plan.baseline_status == "unknown"
    assert row.status == "needs_choice" and row.decision is None


def test_agent_override_is_an_explicit_conflict_and_package_choice_updates_only_shared_field(tmp_path):
    package, _ = _make_package(tmp_path, "incoming", instruction="# Incoming\n")
    _, store, config, host = _receiver(tmp_path)
    config["codex_overrides"] = {"approval_policy": "local-choice"}
    config_path = Path(config["codex"]) / "config.toml"
    config_path.write_text('approval_policy = "on-request"\n', encoding="utf-8")
    (store / "codex" / "config.toml").write_text('approval_policy = "on-request"\n', encoding="utf-8")
    mapping = plan_package_mappings(package, store_root=store, device_config=config, host=host)
    assert mapping.status == "blocked"
    snapshot = inspect_package_targets(package, mapping, store_root=store)

    preview = plan_package_conflicts(package, mapping, snapshot)
    conflict_key = "agent:settings://codex/main/approval_policy"
    row = next(row for row in preview.rows if row.key == conflict_key)
    assert row.status == "needs_choice" and row.decision is None
    assert not preview.can_apply_to_agents

    resolved = plan_package_conflicts(
        package, mapping, snapshot, decisions={conflict_key: "use_package"}
    )
    assert resolved.can_apply_to_agents
    assert "approval_policy" not in resolved.proposed_device_config["codex_overrides"]
    assert "approval_policy" in resolved.proposed_device_config["codex_keys"]
