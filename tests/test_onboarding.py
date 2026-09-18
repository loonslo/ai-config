"""Regression tests for optional memory onboarding and project continuation.

These tests never touch a real memory repository or tool directory.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sync_core import onboarding
from sync_core.config import DeviceConfig


def _config(tmp_path: Path, *, memories=(), projects=None) -> dict:
    codex = tmp_path / "codex"
    codex.mkdir(exist_ok=True)
    return {
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
        "memories": list(memories),
        "projects": dict(projects or {}),
    }


# --------------------------------------------------------------------------
# TASK-15: memory onboarding
# --------------------------------------------------------------------------

def test_configuration_can_be_used_without_any_memory_source(tmp_path):
    raw = _config(tmp_path)
    rows = onboarding.candidate_sources(DeviceConfig(raw, None))
    assert rows == []
    text = "\n".join(onboarding.describe_sources(rows))
    assert "可以先只使用配置同步" in text


def test_claude_and_codex_capabilities_are_stated_differently(tmp_path):
    claude_dir = tmp_path / "claude" / "projects" / "proj" / "memory"
    claude_dir.mkdir(parents=True)
    (claude_dir / "a.md").write_text("note")
    codex_memory = tmp_path / "codex" / "memories"
    codex_memory.mkdir(parents=True)
    raw = _config(tmp_path)
    raw["claude"] = str(tmp_path / "claude")
    raw["codex_memory"] = str(codex_memory)
    rows = onboarding.candidate_sources(DeviceConfig(raw, None))
    by_tool = {row["tool"]: row for row in rows}
    assert "双向同步" in by_tool["claude"]["capability"]
    assert "参考快照" in by_tool["codex"]["capability"]
    assert "原生" not in by_tool["claude"]["capability"]


def test_blocked_source_cannot_be_enabled_and_shows_a_reason(tmp_path):
    blocked = tmp_path / "claude" / "projects" / "secret" / "memory"
    blocked.mkdir(parents=True)
    (blocked / "creds.md").write_text("SERVICE_PASSWORD=verysecretvalue")
    raw = _config(tmp_path)
    raw["claude"] = str(tmp_path / "claude")
    rows = onboarding.candidate_sources(DeviceConfig(raw, None))
    entry = next(row for row in rows if row["status"] == "blocked_secret")
    assert entry["enableable"] is False
    assert entry["reason"]


def test_a_secret_bearing_source_is_never_downgraded_to_just_needing_mapping(tmp_path):
    """A blocked scan must stay blocked, not become "confirm and sync"."""
    blocked = tmp_path / "claude" / "projects" / "secret" / "memory"
    blocked.mkdir(parents=True)
    (blocked / "creds.md").write_text("SERVICE_PASSWORD=verysecretvalue")
    raw = _config(tmp_path)
    raw["claude"] = str(tmp_path / "claude")
    rows = onboarding.candidate_sources(DeviceConfig(raw, None))
    assert [row["status"] for row in rows] == ["blocked_secret"]
    assert rows[0]["needs_mapping"] is False

    # The underlying inventory must agree, so `doctor` keeps reporting it.
    from sync_core.inventory import discover

    inventory = discover(DeviceConfig(raw, None))
    statuses = {source["source_id"]: source["status"] for source in inventory["sources"]}
    assert statuses["claude-unmapped:secret"] == "blocked_secret"


def test_a_source_containing_an_unverified_file_type_is_not_enableable(tmp_path):
    source = tmp_path / "claude" / "projects" / "mixed" / "memory"
    source.mkdir(parents=True)
    (source / "notes.md").write_text("ok")
    (source / "dump.sqlite").write_bytes(b"\x00\x01")
    raw = _config(tmp_path)
    raw["claude"] = str(tmp_path / "claude")
    rows = onboarding.candidate_sources(DeviceConfig(raw, None))
    entry = rows[0]
    assert entry["status"] == "unsupported"
    assert entry["enableable"] is False


def test_a_new_project_can_be_appended_without_inventing_an_id(tmp_path):
    plan = onboarding.plan_memory_enable(
        config=_config(tmp_path),
        selections=[{"path": str(tmp_path / "claude" / "projects" / "My New Project" / "memory")}],
    )
    assert plan["status"] == "ready"
    assert plan["mappings"][0]["id"] == "my-new-project"


def test_duplicate_project_ids_are_rejected(tmp_path):
    plan = onboarding.plan_memory_enable(
        config=_config(tmp_path),
        selections=[
            {"id": "proj", "path": str(tmp_path / "a")},
            {"id": "proj", "path": str(tmp_path / "b")},
        ],
    )
    assert len(plan["mappings"]) == 1
    assert plan["rejected"][0]["reason"].startswith("项目标识重复")


def test_disabling_memory_keeps_the_original_data():
    report = onboarding.disable_memory({"memories": [{"id": "proj", "path": "/x"}]})
    assert report["status"] == "disabled"
    assert report["removed_mappings"] == ["proj"]
    assert "未删除任何内容" in report["note"]


# --------------------------------------------------------------------------
# TASK-16: project continuation
# --------------------------------------------------------------------------

def _write_handoff(memory_repo: Path, project_id: str, handoff_id: str, *, created_at: str, status="uploaded", missing=None) -> None:
    directory = memory_repo / "handoffs" / project_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{handoff_id}.json").write_text(json.dumps({
        "schema_version": 1,
        "handoff_id": handoff_id,
        "project_id": project_id,
        "created_at": created_at,
        "status": status,
        "memory_snapshot": "snap" + handoff_id,
        "missing_fields": missing or [],
    }))
    (directory / f"{handoff_id}.md").write_text(
        "# Handoff\n\n## Goal\nship the feature\n## Completed\nwrote code\n"
        "## Remaining\nreview\n## Next step\nrun tests\n"
    )


def test_projects_can_be_selected_without_typing_internal_ids(tmp_path):
    raw = _config(tmp_path, projects={"myproject": str(tmp_path / "proj")})
    rows = onboarding.list_projects(raw)
    assert len(rows) == 1
    assert rows[0]["project_id"] == "myproject"
    assert rows[0]["name"] == "proj"
    assert rows[0]["has_memory"] is False


def test_continuation_reads_the_latest_handoff_and_shows_context(tmp_path):
    memory_repo = tmp_path / "memory"
    _write_handoff(memory_repo, "myproject", "aaa", created_at="2026-09-01T00:00:00+00:00")
    _write_handoff(memory_repo, "myproject", "bbb", created_at="2026-09-10T00:00:00+00:00")
    report = onboarding.continuation_report(_config(tmp_path), memory_repo, project_id="myproject")
    assert report["status"] == "ready"
    assert report["handoff_id"] == "bbb"
    assert report["goal"] == "ship the feature"
    assert report["next_step"] == "run tests"
    assert len(report["available_handoffs"]) == 2


def test_missing_material_is_not_reported_as_fully_continuable(tmp_path):
    memory_repo = tmp_path / "memory"
    _write_handoff(memory_repo, "myproject", "ccc", created_at="2026-09-10T00:00:00+00:00", status="incomplete", missing=["risks"])
    report = onboarding.continuation_report(_config(tmp_path), memory_repo, project_id="myproject")
    assert report["ready"] is False
    assert report["status"] == "incomplete"


def test_a_project_without_handoffs_is_unavailable(tmp_path):
    report = onboarding.continuation_report(_config(tmp_path), tmp_path / "memory", project_id="ghost")
    assert report["status"] == "unavailable"
    assert report["ready"] is False
    assert "没有可用" in report["reason"]


def test_history_is_not_confused_with_the_current_handoff(tmp_path):
    memory_repo = tmp_path / "memory"
    _write_handoff(memory_repo, "myproject", "old", created_at="2026-01-01T00:00:00+00:00")
    _write_handoff(memory_repo, "myproject", "new", created_at="2026-09-01T00:00:00+00:00")
    report = onboarding.continuation_report(_config(tmp_path), memory_repo, project_id="myproject", handoff_id="old")
    assert report["handoff_id"] == "old"
    assert {row["handoff_id"] for row in report["available_handoffs"]} == {"old", "new"}


def test_unknown_handoff_id_is_rejected_with_a_reason(tmp_path):
    memory_repo = tmp_path / "memory"
    _write_handoff(memory_repo, "myproject", "aaa", created_at="2026-09-01T00:00:00+00:00")
    report = onboarding.continuation_report(_config(tmp_path), memory_repo, project_id="myproject", handoff_id="zzz")
    assert report["ready"] is False
    assert "未找到交接记录" in report["reason"]
