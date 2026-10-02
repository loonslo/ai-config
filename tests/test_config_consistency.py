"""Regression tests for the configuration-consistency tasks (TASK-01 .. TASK-04).

Every test works in an isolated directory and never touches a real tool
configuration or the user's home directory.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sync_core import config_status, environment, messages, status
from sync_core.config import managed_fields, selected_claude_keys, selected_codex_keys


# --------------------------------------------------------------------------
# TASK-01: state structure, versions and independent capabilities
# --------------------------------------------------------------------------

def _state(**overrides):
    payload = {
        "device_id": "windows-a",
        "source": {"type": "git", "identity": "example/repo", "status": "applied"},
        "capabilities": {
            "config": status.capability(enabled=True, status="applied"),
            "memory": status.capability(enabled=False, status="not_configured"),
            "handoff": status.capability(enabled=False, status="not_configured"),
        },
        "managed": {"shared_fields": {"rules": ["instructions"]}, "targets": []},
    }
    payload.update(overrides)
    return status.build_state(**payload)


def test_state_version_is_verifiable_and_unknown_versions_are_rejected():
    state = _state()
    assert status.upgrade_check(state) == "1"
    for bad_version in (2, 99, "1", None):
        broken = dict(state, schema_version=bad_version)
        with pytest.raises(status.StateSchemaError, match="version|integer"):
            status.validate_state(broken)


def test_config_status_succeeds_while_memory_is_disabled():
    state = _state()
    assert state["capabilities"]["memory"]["enabled"] is False
    assert state["capabilities"]["config"]["status"] == "applied"
    # Disabling memory must not force a combined "ready" flag.
    assert "ready" not in json.dumps(state)


def test_every_capability_must_be_reported_separately():
    with pytest.raises(status.StateSchemaError, match="every capability"):
        status.build_state(
            device_id="mac",
            source={"type": "git", "identity": "x", "status": "applied"},
            capabilities={"config": status.capability(enabled=True, status="applied")},
            managed={"shared_fields": {}, "targets": []},
        )


def test_unknown_capability_status_is_rejected():
    with pytest.raises(status.StateSchemaError, match="Unknown capability status"):
        status.capability(enabled=True, status="ready")


def test_shared_receipt_drops_real_paths_and_observed_values():
    state = _state(
        managed={
            "shared_fields": {"rules": ["instructions"]},
            "last_applied_version": "abc123",
            "last_applied_at": "2026-09-15T00:00:00+00:00",
            "targets": [{
                "tool": "claude",
                "target": r"C:\Users\so\.claude\CLAUDE.md",
                "target_kind": "rules_block",
                "fields": ["rules"],
                "status": "applied",
                "expected_digest": "e" * 64,
                "observed_digest": "o" * 64,
                "detail": "local only",
            }],
        }
    )
    receipt = status.shared_receipt(state)
    assert status.receipt_is_sensitive_free(receipt)
    serialized = json.dumps(receipt)
    assert r"C:\\Users\\so" not in serialized
    assert "observed_digest" not in serialized
    assert receipt["target_digests"][0]["expected_digest"] == "e" * 64


# --------------------------------------------------------------------------
# TASK-02: managed fields come from the real device selection
# --------------------------------------------------------------------------

def test_selected_keys_reflect_the_device_choice_not_the_allowlist():
    device = {"codex": "C:/codex", "claude": "C:/claude", "codex_keys": ["web_search"], "claude_keys": []}
    assert selected_codex_keys(device) == ("web_search",)
    assert selected_claude_keys(device) == ()
    fields = managed_fields(device)
    assert fields["codex"] == ["web_search"]
    assert fields["claude"] == []
    assert "approval_policy" not in fields["codex"]


def test_two_devices_with_different_selections_are_distinguishable():
    from sync_core.handoff import configuration_content_version

    first = {"files": {"common/instructions.md": "h"}, "codex_keys": ["web_search"], "claude_keys": []}
    second = {"files": {"common/instructions.md": "h"}, "codex_keys": [], "claude_keys": ["autoMemoryEnabled"]}
    assert configuration_content_version(first) != configuration_content_version(second)


def test_credentials_and_session_fields_cannot_become_shared_fields():
    for field in ("auth_token", "api_key", "password", "session", "credentials"):
        with pytest.raises(ValueError):
            selected_claude_keys({"claude_keys": [field]})
        with pytest.raises(ValueError):
            selected_codex_keys({"codex_keys": [field]})


def test_unverified_tool_parameter_is_not_managed_by_default():
    with pytest.raises(ValueError, match="not a verified shared parameter"):
        selected_codex_keys({"codex_keys": ["some_new_setting"]})


# --------------------------------------------------------------------------
# TASK-03: target verification and drift detection
# --------------------------------------------------------------------------

def _projection(payload: dict) -> dict:
    return payload


def test_target_edit_is_detected_as_local_modification(tmp_path):
    target = tmp_path / "CLAUDE.md"
    expected_block = b"<!-- ai-config:begin -->\nmanaged v2\n<!-- ai-config:end -->"
    target.write_bytes(b"user text\n\n<!-- ai-config:begin -->\nmanaged v1\n<!-- ai-config:end -->\n")
    record = config_status.inspect_target(
        {"tool": "claude", "target": str(target), "target_kind": "rules_block", "fields": ["rules"]},
        expected_projection=expected_block,
    )
    assert record["status"] == "local_modified"
    assert record["observed_digest"] != record["expected_digest"]


def test_matching_target_is_reported_applied(tmp_path):
    target = tmp_path / "CLAUDE.md"
    block = b"<!-- ai-config:begin -->\nmanaged\n<!-- ai-config:end -->"
    target.write_bytes(b"prefix\n\n" + block + b"\n")
    record = config_status.inspect_target(
        {"tool": "claude", "target": str(target), "target_kind": "rules_block", "fields": ["rules"]},
        expected_projection=block,
    )
    assert record["status"] == "applied"


def test_unmanaged_comments_and_fields_do_not_raise_a_false_alarm(tmp_path):
    target = tmp_path / "CLAUDE.md"
    block = b"<!-- ai-config:begin -->\nmanaged\n<!-- ai-config:end -->"
    # A later, unrelated comment edit outside the block must not be drift.
    target.write_bytes(b"# my own note edited later\n\n" + block + b"\n")
    record = config_status.inspect_target(
        {"tool": "claude", "target": str(target), "target_kind": "rules_block", "fields": ["rules"]},
        expected_projection=block,
    )
    assert record["status"] == "applied"


def test_missing_target_is_never_treated_as_applied(tmp_path):
    record = config_status.inspect_target(
        {"tool": "codex", "target": str(tmp_path / "AGENTS.md"), "target_kind": "rules_block", "fields": ["rules"]},
        expected_projection=b"<!-- ai-config:begin -->\nx\n<!-- ai-config:end -->",
    )
    assert record["status"] == "not_configured"
    assert record["observed_digest"] is None


def test_toml_target_only_compares_selected_keys(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text('web_search = "cached"\nmodel_provider = "mine"\n')
    fields = ("web_search",)
    matching = config_status.inspect_target(
        {"tool": "codex", "target": str(target), "target_kind": "config", "fields": list(fields)},
        expected_projection={"web_search": "cached"},
    )
    assert matching["status"] == "applied"
    # An unmanaged provider change is not configuration drift.
    target.write_text('web_search = "cached"\nmodel_provider = "changed"\n')
    still_matching = config_status.inspect_target(
        {"tool": "codex", "target": str(target), "target_kind": "config", "fields": list(fields)},
        expected_projection={"web_search": "cached"},
    )
    assert still_matching["status"] == "applied"


def test_json_target_detects_managed_key_drift(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"autoMemoryEnabled": True, "other": 1}))
    changed = config_status.inspect_target(
        {"tool": "claude", "target": str(target), "target_kind": "settings", "fields": ["autoMemoryEnabled"]},
        expected_projection={"autoMemoryEnabled": False},
    )
    assert changed["status"] == "local_modified"
    target.write_text(json.dumps({"autoMemoryEnabled": False, "other": 2}))
    ok = config_status.inspect_target(
        {"tool": "claude", "target": str(target), "target_kind": "settings", "fields": ["autoMemoryEnabled"]},
        expected_projection={"autoMemoryEnabled": False},
    )
    assert ok["status"] == "applied"


def test_target_behind_the_source_is_pending_not_modified(tmp_path):
    target = tmp_path / "CLAUDE.md"
    applied = b"<!-- ai-config:begin -->\nold\n<!-- ai-config:end -->"
    target.write_bytes(applied + b"\n")
    from sync_core.utils import digest

    record = config_status.inspect_target(
        {"tool": "claude", "target": str(target), "target_kind": "rules_block", "fields": ["rules"]},
        expected_projection=b"<!-- ai-config:begin -->\nnew\n<!-- ai-config:end -->",
        last_applied_digest=digest(applied),
    )
    assert record["status"] == "pending_sync"


def test_malformed_managed_block_reports_failure_not_success(tmp_path):
    target = tmp_path / "CLAUDE.md"
    marker = b"<!-- ai-config:begin -->"
    end = b"<!-- ai-config:end -->"
    target.write_bytes(marker + b"a" + end + marker + b"b" + end)
    record = config_status.inspect_target(
        {"tool": "claude", "target": str(target), "target_kind": "rules_block", "fields": ["rules"]},
        expected_projection=marker + b"x" + end,
    )
    assert record["status"] == "apply_failed"


def test_unreadable_target_is_unknown_not_success(tmp_path, monkeypatch):
    target = tmp_path / "CLAUDE.md"
    target.write_text("x")
    monkeypatch.setattr(config_status, "_read", lambda path: (_ for _ in ()).throw(config_status.TargetUnreadable("locked")))
    record = config_status.inspect_target(
        {"tool": "claude", "target": str(target), "target_kind": "rules_block", "fields": ["rules"]},
        expected_projection=b"<!-- ai-config:begin -->\nx\n<!-- ai-config:end -->",
    )
    assert record["status"] == "apply_failed"
    assert "cannot be read" in record["detail"]


def test_scope_targets_lists_only_configured_tools():
    targets = config_status.scope_targets({"codex": "C:/codex", "claude": "C:/claude", "codex_keys": [], "claude_keys": []})
    kinds = sorted(target["target_kind"] for target in targets)
    assert kinds == ["config", "rules_block", "rules_block", "settings"]
    only_codex = config_status.scope_targets({"codex": "C:/codex", "codex_keys": []})
    assert all(target["tool"] == "codex" for target in only_codex)


# --------------------------------------------------------------------------
# TASK-04: environment detection is read-only and explains itself
# --------------------------------------------------------------------------

def test_detection_performs_no_writes(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    report = environment.detect(configured={}, home=home)
    # Missing tool roots must not be created by detection.
    assert not (home / ".codex").exists()
    assert not (home / ".claude").exists()
    assert report["read_only"] is True


def test_custom_tool_root_from_environment_is_respected(tmp_path, monkeypatch):
    custom = tmp_path / "custom-codex"
    custom.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(custom))
    report = environment.detect(configured={}, home=tmp_path / "home")
    codex = next(tool for tool in report["tools"] if tool["tool"] == "codex")
    assert Path(codex["root"]) == custom
    assert codex["root_exists"] is True
    assert codex["root_origin"] == "环境变量 CODEX_HOME"


def test_single_tool_installation_reports_the_other_as_absent(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    report = environment.detect(configured={"claude": str(home / ".claude")}, home=home)
    claude = next(tool for tool in report["tools"] if tool["tool"] == "claude")
    codex = next(tool for tool in report["tools"] if tool["tool"] == "codex")
    assert claude["installed"] is True
    assert codex["root_exists"] is False


def test_missing_dependency_guidance_names_the_platform_action(tmp_path, monkeypatch):
    monkeypatch.setattr(environment, "system_name", lambda: "windows")
    monkeypatch.setattr(environment, "_module_available", lambda name: False)
    report = environment.detect(configured={}, home=tmp_path)
    guidance = {item["code"]: item for item in report["guidance"]}
    assert "PACKAGE_MISSING" in guidance
    assert "pip install" in guidance["PACKAGE_MISSING"]["action"]
    assert report["ready"] is False


def test_missing_git_guidance_is_platform_specific(tmp_path, monkeypatch):
    monkeypatch.setattr(environment.shutil, "which", lambda name: None if name == "git" else "/usr/bin/" + name)
    report = environment.detect(configured={}, home=tmp_path)
    guidance = {item["code"]: item for item in report["guidance"]}
    assert "GIT_MISSING" in guidance
    assert environment.missing_dependency_exit(report) == 2


def test_missing_git_does_not_block_local_offline_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(environment.shutil, "which", lambda name: None if name == "git" else "/usr/bin/" + name)
    report = environment.detect(configured={}, home=tmp_path, require_git=False)
    guidance = {item["code"]: item for item in report["guidance"]}
    assert report["ready"] is True
    assert report["dependencies"]["git"]["required"] is False
    assert guidance["GIT_OPTIONAL"]["level"] == "info"
    assert environment.missing_dependency_exit(report) == 0


# --------------------------------------------------------------------------
# TASK-14 (catalogue): stable codes and no raw tracebacks
# --------------------------------------------------------------------------

def test_message_catalogue_renders_three_part_output():
    message = messages.get("E3001")
    rendered = messages.render(message)
    assert "发生了什么" not in rendered  # heading is localized, not a field label
    assert "原有数据" in rendered and "下一步" in rendered
    assert message.exit_code == 4


def test_json_output_and_exit_codes_agree():
    for code, message in messages.CATALOGUE.items():
        payload = json.loads(messages.json_error(message))
        assert payload["code"] == code
        assert payload["exit_code"] == message.exit_code


def test_exception_classification_never_returns_a_traceback():
    for text in ("target drift detected", "network unreachable", "permission denied", "backup corrupt", "some unknown thing"):
        message = messages.from_exception(RuntimeError(text))
        assert isinstance(message, messages.Message)
        assert "Traceback" not in messages.render(message)


# --------------------------------------------------------------------------
# TASK-03 follow-up: a missing target must never look applied
# --------------------------------------------------------------------------

def test_a_missing_rules_target_is_never_reported_as_applied(tmp_path):
    from sync_core import config_status

    target = {
        "tool": "codex",
        "target": str(tmp_path / "AGENTS.md"),
        "target_kind": "rules_block",
        "fields": ["rules"],
    }
    record = config_status.inspect_target(target, expected_projection=b"<!-- ai-config:begin -->\nx\n<!-- ai-config:end -->")
    assert record["status"] == "not_configured"
    assert record["observed_digest"] is None
    assert record["detail"] == "target file is missing"


def test_a_target_without_any_managed_block_is_pending_not_applied(tmp_path):
    from sync_core import config_status

    path = tmp_path / "AGENTS.md"
    path.write_text("# My own rules\nno managed block here\n")
    target = {"tool": "codex", "target": str(path), "target_kind": "rules_block", "fields": ["rules"]}
    record = config_status.inspect_target(target, expected_projection=b"<!-- ai-config:begin -->\nx\n<!-- ai-config:end -->")
    assert record["status"] == "pending_sync"


def test_a_matching_managed_block_is_applied(tmp_path):
    from sync_core import config_status

    block = b"<!-- ai-config:begin -->\nshared\n<!-- ai-config:end -->"
    path = tmp_path / "AGENTS.md"
    path.write_bytes(b"# local notes\n" + block)
    target = {"tool": "codex", "target": str(path), "target_kind": "rules_block", "fields": ["rules"]}
    record = config_status.inspect_target(target, expected_projection=block)
    assert record["status"] == "applied"


def test_editing_the_managed_block_is_reported_as_local_modified(tmp_path):
    from sync_core import config_status

    expected = b"<!-- ai-config:begin -->\nshared\n<!-- ai-config:end -->"
    path = tmp_path / "AGENTS.md"
    path.write_bytes(b"<!-- ai-config:begin -->\nedited by hand\n<!-- ai-config:end -->")
    target = {"tool": "codex", "target": str(path), "target_kind": "rules_block", "fields": ["rules"]}
    record = config_status.inspect_target(target, expected_projection=expected)
    assert record["status"] == "local_modified"


def test_editing_only_unmanaged_content_does_not_drift(tmp_path):
    from sync_core import config_status

    block = b"<!-- ai-config:begin -->\nshared\n<!-- ai-config:end -->"
    path = tmp_path / "AGENTS.md"
    path.write_bytes(b"# my private notes changed\n" + block + b"\nmore notes\n")
    target = {"tool": "codex", "target": str(path), "target_kind": "rules_block", "fields": ["rules"]}
    record = config_status.inspect_target(target, expected_projection=block)
    assert record["status"] == "applied"


def test_an_apply_is_verified_even_when_one_target_has_no_managed_fields(tmp_path):
    from sync_core.config_sync import _targets_verified

    targets = [
        {"status": "applied", "fields": ["rules"]},
        {"status": "applied", "fields": ["approval_policy"]},
        {"status": "not_configured", "fields": []},
    ]
    assert _targets_verified(targets) is True


def test_an_apply_is_not_verified_when_a_managed_target_is_drifted(tmp_path):
    from sync_core.config_sync import _targets_verified

    targets = [
        {"status": "applied", "fields": ["rules"]},
        {"status": "local_modified", "fields": ["rules"]},
    ]
    assert _targets_verified(targets) is False


def test_an_apply_is_not_verified_when_a_managed_target_is_missing(tmp_path):
    from sync_core.config_sync import _targets_verified

    # A missing file that *should* hold managed fields is a failure, unlike a
    # target whose managed-field selection is genuinely empty.
    targets = [{"status": "not_configured", "fields": ["rules"]}]
    assert _targets_verified(targets) is False


# --------------------------------------------------------------------------
# TASK-03 follow-up: a missing target must never look applied
# --------------------------------------------------------------------------

def test_a_missing_rules_target_is_never_reported_as_applied(tmp_path):
    from sync_core import config_status

    target = {
        "tool": "codex",
        "target": str(tmp_path / "AGENTS.md"),
        "target_kind": "rules_block",
        "fields": ["rules"],
    }
    record = config_status.inspect_target(target, expected_projection=b"<!-- ai-config:begin -->\nx\n<!-- ai-config:end -->")
    assert record["status"] == "not_configured"
    assert record["observed_digest"] is None
    assert record["detail"] == "target file is missing"


def test_a_target_without_any_managed_block_is_pending_not_applied(tmp_path):
    from sync_core import config_status

    path = tmp_path / "AGENTS.md"
    path.write_text("# My own rules\nno managed block here\n")
    target = {"tool": "codex", "target": str(path), "target_kind": "rules_block", "fields": ["rules"]}
    record = config_status.inspect_target(target, expected_projection=b"<!-- ai-config:begin -->\nx\n<!-- ai-config:end -->")
    assert record["status"] == "pending_sync"


def test_a_matching_managed_block_is_applied(tmp_path):
    from sync_core import config_status

    block = b"<!-- ai-config:begin -->\nshared\n<!-- ai-config:end -->"
    path = tmp_path / "AGENTS.md"
    path.write_bytes(b"# local notes\n" + block)
    target = {"tool": "codex", "target": str(path), "target_kind": "rules_block", "fields": ["rules"]}
    record = config_status.inspect_target(target, expected_projection=block)
    assert record["status"] == "applied"


def test_editing_the_managed_block_is_reported_as_local_modified(tmp_path):
    from sync_core import config_status

    expected = b"<!-- ai-config:begin -->\nshared\n<!-- ai-config:end -->"
    path = tmp_path / "AGENTS.md"
    path.write_bytes(b"<!-- ai-config:begin -->\nedited by hand\n<!-- ai-config:end -->")
    target = {"tool": "codex", "target": str(path), "target_kind": "rules_block", "fields": ["rules"]}
    record = config_status.inspect_target(target, expected_projection=expected)
    assert record["status"] == "local_modified"


def test_editing_only_unmanaged_content_does_not_drift(tmp_path):
    from sync_core import config_status

    block = b"<!-- ai-config:begin -->\nshared\n<!-- ai-config:end -->"
    path = tmp_path / "AGENTS.md"
    path.write_bytes(b"# my private notes changed\n" + block + b"\nmore notes\n")
    target = {"tool": "codex", "target": str(path), "target_kind": "rules_block", "fields": ["rules"]}
    record = config_status.inspect_target(target, expected_projection=block)
    assert record["status"] == "applied"


def test_an_apply_is_verified_even_when_one_target_has_no_managed_fields(tmp_path):
    from sync_core.config_sync import _targets_verified

    targets = [
        {"status": "applied", "fields": ["rules"]},
        {"status": "applied", "fields": ["approval_policy"]},
        {"status": "not_configured", "fields": []},
    ]
    assert _targets_verified(targets) is True


def test_an_apply_is_not_verified_when_a_managed_target_is_drifted(tmp_path):
    from sync_core.config_sync import _targets_verified

    targets = [
        {"status": "applied", "fields": ["rules"]},
        {"status": "local_modified", "fields": ["rules"]},
    ]
    assert _targets_verified(targets) is False


def test_an_apply_is_not_verified_when_a_managed_target_is_missing(tmp_path):
    from sync_core.config_sync import _targets_verified

    # A missing file that *should* hold managed fields is a failure, unlike a
    # target whose managed-field selection is genuinely empty.
    targets = [{"status": "not_configured", "fields": ["rules"]}]
    assert _targets_verified(targets) is False
