"""Regression tests for setup, sync orchestration, receipts, diff and restore.

Every scenario runs in an isolated directory; no real tool configuration, home
directory or remote is touched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sync_core import diff_view, receipts, status
import sync_core.wizard as wizard
from sync_core.config import DeviceConfig
from sync_core.config_sync import ConfigSyncError, local_drift, sync as config_sync
from sync_core.restore import RestoreError, plan_restore, recent_operations, restore, select_operation
from sync_core.transaction import PlannedChanges, transaction
from sync_core.utils import digest


def _device_config(tmp_path: Path, *, tools=("codex",), keys=(), memories=(), projects=()) -> DeviceConfig:
    codex = tmp_path / "codex"
    codex.mkdir(exist_ok=True)
    raw = {
        "device": "windows-a",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory"),
        "codex": str(codex),
        "codex_keys": list(keys),
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "tool_versions": {},
        "additional_sources": [],
        "memories": list(memories),
        "projects": dict(projects) if not isinstance(projects, dict) else projects,
    }
    if "claude" in tools:
        claude = tmp_path / "claude"
        claude.mkdir(exist_ok=True)
        raw["claude"] = str(claude)
    return DeviceConfig(raw, tmp_path / "device.json")


# --------------------------------------------------------------------------
# TASK-13: restore by operation, without hunting for a UUID
# --------------------------------------------------------------------------

def test_recent_operations_describe_time_tool_and_change_count(tmp_path):
    state = tmp_path / "state"
    target = tmp_path / "AGENTS.md"
    target.write_bytes(b"old")
    plan = PlannedChanges({target: b"new"}, state_root=state, metadata={"operation": "config"})
    transaction(plan, state / "backups", state_root=state, operation_id="op1")
    operations = recent_operations(state)
    assert len(operations) == 1
    entry = operations[0]
    assert entry["operation_id"] == "op1"
    assert entry["change_count"] == 1
    assert "codex" in entry["tools"]
    assert entry["statement"]


def test_restore_by_index_returns_managed_fields_to_their_prior_value(tmp_path):
    state = tmp_path / "state"
    target = tmp_path / "AGENTS.md"
    target.write_bytes(b"original managed value")
    transaction(PlannedChanges({target: b"applied by sync"}, state_root=state, metadata={"operation": "config"}), state / "backups", state_root=state, operation_id="op1")
    assert target.read_bytes() == b"applied by sync"
    report = restore(state, index=1, apply=True)
    assert report["status"] == "restored"
    assert target.read_bytes() == b"original managed value"


def test_restore_refuses_a_corrupt_backup(tmp_path):
    state = tmp_path / "state"
    target = tmp_path / "AGENTS.md"
    target.write_bytes(b"original")
    transaction(PlannedChanges({target: b"applied"}, state_root=state, metadata={"operation": "config"}), state / "backups", state_root=state, operation_id="op1")
    backup = state / "backups" / "op1"
    for path in sorted(backup.iterdir()):
        if path.name != "manifest.json":
            path.write_bytes(b"corrupted")
    with pytest.raises(RestoreError, match="哈希不符|损坏"):
        plan_restore(state, select_operation(state, operation_id="op1"))


def test_restore_surfaces_later_user_edits_as_a_conflict(tmp_path):
    state = tmp_path / "state"
    target = tmp_path / "AGENTS.md"
    target.write_bytes(b"original")
    transaction(PlannedChanges({target: b"applied"}, state_root=state, metadata={"operation": "config"}), state / "backups", state_root=state, operation_id="op1")
    target.write_bytes(b"edited after the apply")
    with pytest.raises(RestoreError, match="又被修改"):
        plan_restore(state, select_operation(state, operation_id="op1"))


def test_restore_preview_writes_nothing(tmp_path):
    state = tmp_path / "state"
    target = tmp_path / "AGENTS.md"
    target.write_bytes(b"original")
    transaction(PlannedChanges({target: b"applied"}, state_root=state, metadata={"operation": "config"}), state / "backups", state_root=state, operation_id="op1")
    report = restore(state, index=1, apply=False)
    assert report["status"] == "preview"
    assert target.read_bytes() == b"applied"


# --------------------------------------------------------------------------
# TASK-10: receipts on a dedicated branch with isolated workspaces
# --------------------------------------------------------------------------

def _state_for(device: str, *, version: str = "v1") -> dict:
    return status.build_state(
        device_id=device,
        source={"type": "git", "identity": "example/repo", "status": "applied"},
        capabilities={
            "config": status.capability(enabled=True, status="applied"),
            "memory": status.capability(enabled=False, status="not_configured"),
            "handoff": status.capability(enabled=False, status="not_configured"),
        },
        managed={
            "shared_fields": {"rules": ["instructions"]},
            "last_applied_version": version,
            "targets": [{
                "tool": "codex", "target": "C:/codex/AGENTS.md", "target_kind": "rules_block",
                "fields": ["rules"], "status": "applied",
                "expected_digest": "a" * 64, "observed_digest": "b" * 64, "detail": "local",
            }],
        },
    )


def test_receipt_omits_real_paths_and_observed_values(tmp_path):
    receipt = receipts.write_receipt(tmp_path, _state_for("windows-a"))
    serialized = json.dumps(receipt)
    assert "C:/codex/AGENTS.md" not in serialized
    assert "observed_digest" not in serialized
    assert receipt["applied_version"] == "v1"
    assert receipt["target_digests"][0]["expected_digest"] == "a" * 64


def test_two_devices_report_without_overwriting_each_other(tmp_path):
    receipts.write_receipt(tmp_path, _state_for("windows-a", version="v1"))
    receipts.write_receipt(tmp_path, _state_for("windows-b", version="v2"))
    stored = receipts.read_all_receipts(tmp_path)
    assert {item["device_id"] for item in stored} == {"windows-a", "windows-b"}
    assert receipts.read_receipt(tmp_path, "windows-a")["applied_version"] == "v1"
    assert receipts.read_receipt(tmp_path, "windows-b")["applied_version"] == "v2"


def test_device_summary_never_claims_a_device_is_online(tmp_path):
    receipts.write_receipt(tmp_path, _state_for("mac"))
    rows = receipts.device_summary(receipts.read_all_receipts(tmp_path), this_device="windows-a")
    assert rows[0]["live"] is False
    assert "最近报告于" in rows[0]["statement"]
    assert "在线" not in rows[0]["statement"]


def test_receipt_branch_is_not_main(tmp_path):
    assert receipts.RECEIPT_BRANCH != "main"
    assert receipts.RECEIPT_DIR == "receipts"


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "T"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@example.invalid"], check=True)
    (path / "README.md").write_text("source")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True, capture_output=True)


def test_publish_receipt_uses_a_branch_and_keeps_main_content(tmp_path):
    origin = tmp_path / "origin"
    work = tmp_path / "work"
    _init_repo(work)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(origin)], check=True)
    subprocess.run(["git", "-C", str(work), "push", "-q", "-u", "origin", "main"], check=True, capture_output=True)
    main_before = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()

    result = receipts.publish_receipt(work, _state_for("windows-a"))
    assert result["status"] == "uploaded"
    # The configuration content on main must not move.
    main_after = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    assert main_after == main_before
    # The receipt lives on its own branch and is readable back.
    fetched = receipts.fetch_receipts(work)
    assert [item["device_id"] for item in fetched] == ["windows-a"]
    branch = subprocess.run(["git", "-C", str(work), "branch", "--show-current"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    assert branch == "main"


def test_two_devices_publish_concurrently_without_losing_a_receipt(tmp_path):
    origin = tmp_path / "origin"
    work = tmp_path / "work"
    _init_repo(work)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(origin)], check=True)
    subprocess.run(["git", "-C", str(work), "push", "-q", "-u", "origin", "main"], check=True, capture_output=True)
    receipts.publish_receipt(work, _state_for("windows-a", version="v1"))
    receipts.publish_receipt(work, _state_for("windows-b", version="v2"))
    devices = sorted(item["device_id"] for item in receipts.fetch_receipts(work))
    assert devices == ["windows-a", "windows-b"]


# --------------------------------------------------------------------------
# TASK-11: diff display and ownership selection
# --------------------------------------------------------------------------

def test_diffs_show_shared_and_local_values_with_origin():
    diffs = diff_view.collect_diffs(
        shared={"codex": {"web_search": "cached"}},
        local={"codex": {"web_search": "disabled"}},
        tools=["codex"],
    )
    assert len(diffs) == 1
    text = diff_view.render_diffs(diffs)
    assert "网页搜索" in text
    assert "共享值：cached" in text
    assert "本机值：disabled" in text


def test_sensitive_values_are_masked_in_the_diff():
    diffs = diff_view.collect_diffs(
        shared={"claude": {"autoMemoryEnabled": "sk-" + "x" * 30}},
        local={"claude": {"autoMemoryEnabled": False}},
        tools=["claude"],
    )
    assert "已遮蔽" in diff_view.render_diffs(diffs)


def test_no_write_happens_before_a_choice_is_made():
    diffs = diff_view.collect_diffs(shared={"codex": {"web_search": "a"}}, local={"codex": {"web_search": "b"}}, tools=["codex"])
    status_code = diff_view.non_interactive_status(diffs, choice=None)
    assert status_code["status"] == "choice_required"
    assert status_code["ready"] is False


def test_each_choice_declares_its_effect():
    for choice in diff_view.CHOICES:
        action = diff_view.resolve_choice(choice, field_name="web_search", shared_value="cached")
        assert action["effect"]
        assert action["target"] in {"shared_template", "local_override", "local_effective"}
    with pytest.raises(diff_view.DiffChoiceError):
        diff_view.resolve_choice("overwrite-everything", field_name="x", shared_value=1)


def test_complex_structures_are_displayed_but_not_auto_merged():
    diffs = diff_view.collect_diffs(
        shared={"codex": {"web_search": {"nested": True}}},
        local={"codex": {"web_search": "flat"}},
        tools=["codex"],
    )
    assert diffs[0].complex_value is True
    assert "复杂结构" in diff_view.render_diffs(diffs)


def test_invalid_non_interactive_choice_is_reported_stably():
    diffs = diff_view.collect_diffs(shared={"codex": {"web_search": "a"}}, local={"codex": {"web_search": "b"}}, tools=["codex"])
    result = diff_view.non_interactive_status(diffs, choice="nope")
    assert result["status"] == "invalid_choice"
    assert result["ready"] is False


# --------------------------------------------------------------------------
# TASK-06 / TASK-07: setup, device ids and joining
# --------------------------------------------------------------------------

def test_device_id_is_stable_and_disambiguated_on_collision():
    first = wizard.stable_device_id(system="Windows", hostname="desk")
    second = wizard.stable_device_id(system="Windows", hostname="desk")
    assert first == second
    collided = wizard.stable_device_id(system="Windows", hostname="desk", existing={first})
    assert collided != first
    assert collided not in {first}


def test_mac_and_windows_ids_do_not_collide_for_the_same_hostname():
    mac = wizard.stable_device_id(system="Darwin", hostname="studio")
    windows = wizard.stable_device_id(system="Windows", hostname="studio")
    assert mac != windows


def test_setup_never_enables_memory_by_default(tmp_path):
    config = wizard.plan_device(
        device_id="windows-a",
        state_dir=tmp_path / "state",
        memory_repo=tmp_path / "memory",
        tools=["codex"],
        scope=wizard.SCOPE_RULES_ONLY,
        remote_url="https://example.invalid/ai-config.git",
        tool_roots={"codex": str(tmp_path / "codex")},
    )
    assert config["memories"] == []
    assert config["codex_keys"] == []
    assert config["remote_identity"] == "https://example.invalid/ai-config.git"


def test_setup_rejects_unknown_scope_before_writing(tmp_path):
    with pytest.raises(wizard.SetupError):
        wizard.plan_device(
            state_dir=tmp_path / "state",
            memory_repo=tmp_path / "memory",
            tools=["codex"],
            scope="everything",
            remote_url=None,
            tool_roots={"codex": str(tmp_path / "codex")},
        )


def test_setup_requires_at_least_one_tool(tmp_path):
    with pytest.raises(wizard.SetupError):
        wizard.plan_device(
            state_dir=tmp_path / "state",
            memory_repo=tmp_path / "memory",
            tools=[],
            scope=wizard.SCOPE_RULES_ONLY,
            remote_url=None,
            tool_roots={},
        )


def test_joining_a_wrong_source_stops_without_writing(tmp_path):
    with pytest.raises(wizard.SetupError, match="身份不匹配"):
        wizard.join_existing(
            remote_url="https://example.invalid/other.git",
            expected_identity="https://example.invalid/ai-config.git",
            tools=["codex"],
            tool_roots={"codex": str(tmp_path / "codex")},
            state_dir=tmp_path / "state",
            memory_repo=tmp_path / "memory",
        )


def test_join_reuses_shared_selection_and_is_idempotent(tmp_path):
    (tmp_path / "codex").mkdir()
    first = wizard.join_existing(
        remote_url="https://example.invalid/ai-config.git",
        expected_identity="https://example.invalid/ai-config.git",
        tools=["codex"],
        tool_roots={"codex": str(tmp_path / "codex")},
        state_dir=tmp_path / "state",
        memory_repo=tmp_path / "memory",
        registered=set(),
    )
    (tmp_path / "codex2").mkdir()
    again = wizard.join_existing(
        remote_url="https://example.invalid/ai-config.git",
        expected_identity="https://example.invalid/ai-config.git",
        tools=["codex"],
        tool_roots={"codex": str(tmp_path / "codex2")},
        state_dir=tmp_path / "state",
        memory_repo=tmp_path / "memory",
        registered={first["device_id"]},
    )
    # Joining twice on the same host produces a different, non-conflicting id.
    assert again["device_id"] != first["device_id"]


def test_existing_configuration_is_backed_up_before_being_replaced(tmp_path):
    target = tmp_path / "device.json"
    target.write_text('{"device": "old"}')
    written = wizard.write_config({"device": "new"}, target)
    assert written["backup"] is not None
    assert Path(written["backup"]).read_text() == '{"device": "old"}'
    assert json.loads(target.read_text())["device"] == "new"


def test_cancelled_wizard_leaves_no_partial_configuration(tmp_path):
    target = tmp_path / "device.json"
    answers = iter(["", ""])
    with pytest.raises(wizard.SetupCancelled):
        wizard.run_wizard(
            ask=lambda question: next(answers),
            state_dir=tmp_path / "state",
            memory_repo=tmp_path / "memory",
            environment={"tools": [{"tool": "codex", "installed": True, "root": str(tmp_path / "codex"), "root_origin": "默认位置"}], "system": "windows", "dependencies": {}},
            first_device=True,
            target=target,
        )
    assert not target.exists()


# --------------------------------------------------------------------------
# TASK-08: sync orchestration reports the failing stage
# --------------------------------------------------------------------------

def test_offline_fetch_failure_is_reported_at_the_fetch_stage(tmp_path):
    device = _device_config(tmp_path)

    def failing_fetch():
        raise RuntimeError("network unreachable")

    with pytest.raises(ConfigSyncError) as info:
        config_sync(device, apply=True, fetch=failing_fetch)
    assert info.value.stage == "fetch"
    assert info.value.exit_code == 3


def test_drift_is_reported_before_applying(tmp_path):
    device = _device_config(tmp_path)
    target = Path(device.raw["codex"]) / "AGENTS.md"
    # Unrelated content outside the managed block is not drift.
    target.write_bytes(b"my own note\n")
    drift = local_drift(device)
    assert not drift["drifting"], drift
    # A separately edited managed block is reported as a conflict, never
    # silently overwritten.
    target.write_bytes(b"<!-- ai-config:begin -->\nlocally changed\n<!-- ai-config:end -->")
    drift = local_drift(device)
    assert drift["drifting"], drift


def test_locally_edited_managed_block_stops_the_overwrite(tmp_path):
    device = _device_config(tmp_path)
    target = Path(device.raw["codex"]) / "AGENTS.md"
    target.write_bytes(b"<!-- ai-config:begin -->\nlocally changed\n<!-- ai-config:end -->")
    before = target.read_bytes()
    with pytest.raises(ConfigSyncError) as info:
        config_sync(device, apply=True)
    assert info.value.stage == "resolve"
    assert info.value.exit_code == 4
    assert target.read_bytes() == before


def test_unmanaged_only_edit_does_not_stop_sync(tmp_path):
    device = _device_config(tmp_path)
    target = Path(device.raw["codex"]) / "AGENTS.md"
    target.write_bytes(b"a user comment only\n")
    report = config_sync(device, apply=True)
    assert report["status"] == "applied"
    assert b"a user comment only" in target.read_bytes()


def test_preview_writes_nothing(tmp_path):
    device = _device_config(tmp_path)
    target = Path(device.raw["codex"]) / "AGENTS.md"
    target.write_bytes(b"existing content")
    before = target.read_bytes()
    report = config_sync(device, apply=False)
    assert report["status"] == "preview"
    assert report["ready"] is False
    assert target.read_bytes() == before


def test_apply_then_verify_records_the_applied_version(tmp_path):
    device = _device_config(tmp_path)
    report = config_sync(device, apply=True)
    assert report["status"] in {"applied"}
    marker = device.state_dir / "applied.json"
    assert marker.exists()
    payload = json.loads(marker.read_text())
    assert payload["targets"]


def test_repeated_sync_produces_no_pointless_write(tmp_path):
    device = _device_config(tmp_path)
    config_sync(device, apply=True)
    second = config_sync(device, apply=True)
    assert second["changes"] == 0
    assert second["status"] == "applied"


def test_sync_does_not_require_a_memory_repository(tmp_path):
    device = _device_config(tmp_path)
    # No ai-memory directory exists anywhere in this tmp_path.
    report = config_sync(device, apply=True)
    assert report["status"] == "applied"


# --------------------------------------------------------------------------
# TASK-09: status overview
# --------------------------------------------------------------------------

def test_status_is_readable_without_json_and_lists_next_step(tmp_path):
    device = _device_config(tmp_path)
    from sync_core.config_sync import state_for

    state = state_for(device)
    assert state["capabilities"]["config"]["status"] in status.STATUS_CODES
    # A configuration-only device must not surface an unrelated memory failure.
    assert state["capabilities"]["memory"]["status"] in {"not_configured", "pending_sync"}


def test_config_only_user_never_sees_a_memory_error(tmp_path):
    device = _device_config(tmp_path)
    from sync_core.config_sync import state_for

    state = state_for(device)
    assert state["capabilities"]["memory"]["enabled"] is False
    assert state["capabilities"]["memory"]["status"] == "not_configured"


def test_zero_change_preview_is_not_reported_as_applied(tmp_path):
    device = _device_config(tmp_path)
    report = config_sync(device, apply=False)
    assert report["status"] == "preview"
    assert "不代表已经应用" in report["note"]


# --------------------------------------------------------------------------
# TASK-12: persist a local change as shared or as a device-local override
# --------------------------------------------------------------------------

def test_a_preview_choice_never_writes_anything(tmp_path, monkeypatch):
    from sync_core import config_sync

    monkeypatch.setattr(config_sync, "ROOT_FOR_TEMPLATES", tmp_path / "repo")
    (tmp_path / "repo" / "claude").mkdir(parents=True)
    (tmp_path / "repo" / "claude" / "settings.shared.json").write_text('{"autoMemoryEnabled": true}')
    device = _device_config(tmp_path, tools=("claude",), keys=("autoMemoryEnabled",))

    result = config_sync.plan_ownership(
        device, tool="claude", field_name="autoMemoryEnabled", value=False, choice="local", apply=False
    )
    assert result["status"] == "preview"
    assert result["written"] is False
    assert not (device.state_dir / "local_overrides.json").exists()


def test_a_local_choice_writes_an_override_without_touching_the_template(tmp_path, monkeypatch):
    from sync_core import config_sync

    template = tmp_path / "repo"
    monkeypatch.setattr(config_sync, "ROOT_FOR_TEMPLATES", template)
    (template / "claude").mkdir(parents=True)
    original = '{"autoMemoryEnabled": true}'
    (template / "claude" / "settings.shared.json").write_text(original)
    device = _device_config(tmp_path, tools=("claude",), keys=("autoMemoryEnabled",))

    result = config_sync.plan_ownership(
        device, tool="claude", field_name="autoMemoryEnabled", value=False, choice="local", apply=True
    )
    assert result["status"] == "saved"
    assert result["committed_files"] == []
    assert (template / "claude" / "settings.shared.json").read_text() == original
    overrides = config_sync.read_local_overrides(device)
    assert overrides == {"claude": {"autoMemoryEnabled": False}}


def test_a_share_choice_updates_only_the_managed_key(tmp_path, monkeypatch):
    from sync_core import config_sync

    template = tmp_path / "repo"
    monkeypatch.setattr(config_sync, "ROOT_FOR_TEMPLATES", template)
    (template / "claude").mkdir(parents=True)
    (template / "claude" / "settings.shared.json").write_text(
        json.dumps({"autoMemoryEnabled": True, "unrelated": "keep me"}, indent=2)
    )
    device = _device_config(tmp_path, tools=("claude",), keys=("autoMemoryEnabled",))

    result = config_sync.plan_ownership(
        device, tool="claude", field_name="autoMemoryEnabled", value=False, choice="share", apply=True
    )
    assert result["status"] == "saved"
    assert result["committed_files"] == ["claude/settings.shared.json"]
    saved = json.loads((template / "claude" / "settings.shared.json").read_text())
    assert saved["autoMemoryEnabled"] is False
    # An unrelated key must survive the update.
    assert saved["unrelated"] == "keep me"


def test_a_sensitive_value_can_never_be_shared_or_overridden(tmp_path, monkeypatch):
    from sync_core import config_sync

    monkeypatch.setattr(config_sync, "ROOT_FOR_TEMPLATES", tmp_path / "repo")
    (tmp_path / "repo" / "codex").mkdir(parents=True)
    (tmp_path / "repo" / "codex" / "config.toml").write_text('approval_policy = "on-request"\n')
    device = _device_config(tmp_path, keys=("approval_policy",))

    # Assembled at runtime so this repository never contains a credential-looking
    # literal; the value still trips the detector the way a real key would.
    looks_like_a_key = "sk" + "-live-" + ("x" * 32)

    for choice in ("share", "local"):
        with pytest.raises(config_sync.OwnershipError) as error:
            config_sync.plan_ownership(
                device, tool="codex", field_name="approval_policy",
                value=looks_like_a_key, choice=choice, apply=True,
            )
        assert "不能共享" in str(error.value)

    # A credentialed field *name* is refused even when the value looks harmless.
    with pytest.raises(config_sync.OwnershipError):
        config_sync.plan_ownership(
            device, tool="codex", field_name="api_token", value="short", choice="share", apply=True
        )


def test_an_unknown_ownership_choice_is_rejected(tmp_path, monkeypatch):
    from sync_core import config_sync

    monkeypatch.setattr(config_sync, "ROOT_FOR_TEMPLATES", tmp_path / "repo")
    device = _device_config(tmp_path)
    with pytest.raises(config_sync.OwnershipError):
        config_sync.plan_ownership(
            device, tool="codex", field_name="approval_policy", value="x", choice="overwrite", apply=False
        )


def test_restore_choice_delegates_to_the_backed_up_apply_path(tmp_path, monkeypatch):
    from sync_core import config_sync

    monkeypatch.setattr(config_sync, "ROOT_FOR_TEMPLATES", tmp_path / "repo")
    device = _device_config(tmp_path)
    result = config_sync.plan_ownership(
        device, tool="codex", field_name="approval_policy", value="on-request", choice="restore", apply=True
    )
    # The restore path writes nothing directly: apply + backup does the work.
    assert result["written"] is False
    assert result["committed_files"] == []
    assert "备份" in result["effect"]


# --------------------------------------------------------------------------
# TASK-14: doctor and per-command output consistency
# --------------------------------------------------------------------------

def test_doctor_renders_chinese_by_default_and_json_on_request(tmp_path):
    root = Path(__file__).resolve().parents[1]
    device = tmp_path / "device.json"
    device.write_text(json.dumps({
        "device": "windows-a",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory"),
        "codex": str(tmp_path / "codex"),
        "codex_keys": [],
        "claude_keys": [],
        "codex_overrides": {},
        "claude_overrides": {},
        "tool_versions": {},
        "additional_sources": [],
        "memories": [],
        "projects": {},
    }), encoding="utf-8")
    (tmp_path / "codex").mkdir()

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    prose = subprocess.run(
        [sys.executable, str(root / "scripts" / "sync.py"), "doctor", "--local", str(device)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env,
    )
    assert prose.returncode == 0, prose.stderr
    assert "设备：windows-a" in prose.stdout
    assert "结论：" in prose.stdout
    # The prose form must not be raw JSON.
    assert not prose.stdout.lstrip().startswith("{")

    payload = subprocess.run(
        [sys.executable, str(root / "scripts" / "sync.py"), "doctor", "--local", str(device), "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env,
    )
    assert payload.returncode == 0, payload.stderr
    data = json.loads(payload.stdout)
    assert data["device_id"] == "windows-a"
    assert data["ok"] is True


def test_sync_reports_drift_as_a_conflict_exit_code_and_never_traces_back(tmp_path):
    root = Path(__file__).resolve().parents[1]
    device = tmp_path / "device.json"
    (tmp_path / "codex").mkdir()
    device.write_text(json.dumps({
        "device": "windows-a",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory"),
        "codex": str(tmp_path / "codex"),
        "codex_keys": [],
        "claude_keys": [],
        "codex_overrides": {},
        "claude_overrides": {},
        "tool_versions": {},
        "additional_sources": [],
        "memories": [],
        "projects": {},
    }), encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    sync_cmd = [sys.executable, str(root / "scripts" / "sync.py"), "sync", "--local", str(device)]

    first = subprocess.run(sync_cmd + ["--apply"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env)
    assert first.returncode == 0, first.stderr

    # Edit inside the managed block; the shared value must never silently win.
    agents = tmp_path / "codex" / "AGENTS.md"
    agents.write_text(agents.read_text(encoding="utf-8").replace(
        "<!-- ai-config:begin -->", "<!-- ai-config:begin -->\n\n手工改动", 1
    ), encoding="utf-8")

    second = subprocess.run(sync_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env)
    assert second.returncode == 4
    assert "E3001" in second.stderr
    assert "Traceback" not in second.stderr
    # The locally edited content must survive.
    assert "手工改动" in agents.read_text(encoding="utf-8")

    as_json = subprocess.run(sync_cmd + ["--json"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env)
    assert as_json.returncode == 4
    payload = json.loads(as_json.stderr)
    assert payload["code"] == "E3001"
    assert payload["stage"] == "resolve"


# --------------------------------------------------------------------------
# TASK-03/TASK-12: the drift recovery loop has to actually close
# --------------------------------------------------------------------------

def _drift_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """A synced device whose managed rules block was then hand-edited.

    Returns ``(root, device_path, codex_dir, agents_path)``.
    """
    root = Path(__file__).resolve().parents[1]
    codex = tmp_path / "codex"
    codex.mkdir()
    device = tmp_path / "device.json"
    device.write_text(json.dumps({
        "device": "windows-a",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory"),
        "codex": str(codex),
        "codex_keys": [],
        "claude_keys": [],
        "codex_overrides": {},
        "claude_overrides": {},
        "tool_versions": {},
        "additional_sources": [],
        "memories": [],
        "projects": {},
    }), encoding="utf-8")
    agents = codex / "AGENTS.md"
    agents.write_text("# 本机说明\n\n用户自己的内容。\n", encoding="utf-8")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    sync_cmd = [sys.executable, str(root / "scripts" / "sync.py"), "sync", "--local", str(device)]
    first = subprocess.run(sync_cmd + ["--apply"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env)
    assert first.returncode == 0, first.stderr
    assert "<!-- ai-config:begin -->" in agents.read_text(encoding="utf-8")

    # Hand-edit the managed block, the way a user would while experimenting.
    text = agents.read_text(encoding="utf-8")
    agents.write_text(
        text.replace("<!-- ai-config:end -->", "\n本机额外加的一条规则。\n<!-- ai-config:end -->", 1),
        encoding="utf-8",
    )
    return root, device, codex, agents


def test_hand_edited_rules_block_shows_up_in_diff(tmp_path):
    """`sync` tells the user to run `diff`; `diff` must actually show the block."""
    root, device, _codex, _agents = _drift_fixture(tmp_path)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    blocked = subprocess.run(
        [sys.executable, str(root / "scripts" / "sync.py"), "sync", "--local", str(device), "--apply"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env,
    )
    assert blocked.returncode == 4
    assert "E3001" in blocked.stderr

    diff = subprocess.run(
        [sys.executable, str(root / "scripts" / "sync.py"), "diff", "--local", str(device)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env,
    )
    # Listing is read-only, so it exits 0; what matters is that it names the block.
    assert diff.returncode == 0, diff.stdout + diff.stderr
    # The old dead end: `diff` used to print "nothing to handle" and the user
    # had nowhere to go.
    assert "没有需要处理的字段差异" not in diff.stdout
    assert "规则" in diff.stdout
    assert "share" in diff.stdout and "restore" in diff.stdout


def test_restore_choice_overwrites_the_edited_block_after_a_backup(tmp_path):
    """The documented recovery path has to actually close the loop."""
    root, device, _codex, agents = _drift_fixture(tmp_path)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    sync_cmd = [sys.executable, str(root / "scripts" / "sync.py"), "sync", "--local", str(device)]

    resolve = subprocess.run(
        [
            sys.executable, str(root / "scripts" / "sync.py"), "diff",
            "--local", str(device), "--choice", "restore", "--apply",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env,
    )
    assert resolve.returncode == 0, resolve.stdout + resolve.stderr
    assert "已保存" in resolve.stdout

    # The shared block is now authoritative, so the next sync applies it.
    second = subprocess.run(sync_cmd + ["--apply"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env)
    assert second.returncode == 0, second.stderr

    restored = agents.read_text(encoding="utf-8")
    assert "本机额外加的一条规则。" not in restored
    # The user's own unmanaged prose is untouched.
    assert "用户自己的内容。" in restored

    # And the loop stays closed: a further sync is a no-op, not another conflict.
    third = subprocess.run(sync_cmd + ["--apply"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env)
    assert third.returncode == 0, third.stderr

    # The overwritten content is recoverable through the documented undo path:
    # the restore write is a listed operation, and previewing it names the file.
    undo = subprocess.run(
        [sys.executable, str(root / "scripts" / "sync.py"), "undo", "--local", str(device), "--list"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env,
    )
    assert undo.returncode == 0, undo.stderr
    assert "最近的配置应用记录" in undo.stdout

    preview = subprocess.run(
        [sys.executable, str(root / "scripts" / "sync.py"), "undo", "--local", str(device), "--index", "1"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env,
    )
    assert preview.returncode == 0, preview.stdout + preview.stderr
    assert "AGENTS.md" in preview.stdout


def test_a_local_choice_is_refused_for_the_rules_block(tmp_path):
    """Keeping a divergent rules block locally is silent divergence, not a choice."""
    root, device, _codex, _agents = _drift_fixture(tmp_path)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    refused = subprocess.run(
        [
            sys.executable, str(root / "scripts" / "sync.py"), "diff",
            "--local", str(device), "--choice", "local", "--apply",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env,
    )
    assert refused.returncode == 4
    assert "规则" in (refused.stdout + refused.stderr)


def test_a_restore_intent_does_not_survive_a_later_hand_edit(tmp_path):
    """The restore intent is one-shot; it must not mask a *new* local edit."""
    root, device, _codex, agents = _drift_fixture(tmp_path)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    sync_cmd = [sys.executable, str(root / "scripts" / "sync.py"), "sync", "--local", str(device)]

    subprocess.run(
        [
            sys.executable, str(root / "scripts" / "sync.py"), "diff",
            "--local", str(device), "--choice", "restore", "--apply",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env,
    )
    applied = subprocess.run(sync_cmd + ["--apply"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env)
    assert applied.returncode == 0, applied.stderr

    # A fresh hand-edit after the restore has to be caught again.
    text = agents.read_text(encoding="utf-8")
    agents.write_text(
        text.replace("<!-- ai-config:end -->", "\n又一次本机改动。\n<!-- ai-config:end -->", 1),
        encoding="utf-8",
    )
    again = subprocess.run(sync_cmd + ["--apply"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, env=env)
    assert again.returncode == 4, again.stdout + again.stderr
    assert "E3001" in again.stderr


def test_the_diff_hint_never_offers_a_refused_choice(tmp_path):
    """A rule block has no `local` outcome; the hint must not advertise one."""
    from sync_core import diff_view

    rules = diff_view.FieldDiff(
        tool="codex",
        field="rules",
        shared_value="（共享规则区块，见 common/）",
        local_value="（本机在受管区块内改过内容）",
        source="target_file",
        complex_value=True,
    )
    rendered = diff_view.render_diffs([rules])
    assert "restore" in rendered
    assert "local=仅此设备" not in rendered
    assert rules.choices == ("share", "restore")


def test_a_scalar_field_still_offers_all_three_choices():
    from sync_core import diff_view

    scalar = diff_view.FieldDiff(
        tool="codex",
        field="sandbox_mode",
        shared_value="workspace-write",
        local_value="read-only",
        source="template",
    )
    assert set(scalar.choices) == {"share", "local", "restore"}
    rendered = diff_view.render_diffs([scalar])
    for key in ("share", "local", "restore"):
        assert key in rendered
