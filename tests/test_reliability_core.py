import json
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import pytest

from sync_core.merge import three_way_merge, validate_file_map
from sync_core.snapshots import create_snapshot, load_snapshot, mark_head_confirmed, restore_snapshot
from sync_core.transaction import PlannedChanges, transaction
from sync_core.utils import digest


def test_plan_hash_and_source_tree_are_checked_before_apply(tmp_path):
    target = tmp_path / "target.md"
    target.write_text("old")
    plan = PlannedChanges(
        {target: b"new"},
        expected={target: digest(b"changed")},
        state_root=tmp_path / "state",
    )
    with pytest.raises(ValueError, match="invalidated"):
        transaction(plan, tmp_path / "state/backups")
    assert target.read_text() == "old"


def test_source_tree_change_invalidates_plan(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    file = source / "a.md"
    file.write_text("old")
    plan = PlannedChanges({tmp_path / "target.md": None}, expected_trees={source: {"a.md": digest(b"old")}}, state_root=tmp_path / "state")
    file.write_text("changed")
    with pytest.raises(ValueError, match="source change"):
        transaction(plan, tmp_path / "state/backups")


def test_delete_last_file_and_collisions():
    old = {"MEMORY.md": digest(b"x")}
    assert three_way_merge({}, {}, old).files == {}
    with pytest.raises(ValueError, match="collision"):
        validate_file_map({"Résumé.md": b"a", unicodedata.normalize("NFD", "Résumé.md"): b"b"})
    with pytest.raises(ValueError, match="collision"):
        validate_file_map({"A.md": b"a", "a.md/topic.md": b"b"})


def test_snapshot_objects_are_immutable_and_restore_does_not_publish(tmp_path):
    manifest = create_snapshot(tmp_path / "memory", device="windows-a", scope="project", project_id="project", files={"MEMORY.md": b"fact"})
    loaded = load_snapshot(tmp_path / "memory", manifest["snapshot_id"])
    object_path = tmp_path / "memory" / "objects" / (manifest["files"][0]["sha256"] + ".md")
    assert object_path.read_bytes() == b"fact"
    with pytest.raises(ValueError):
        create_snapshot(tmp_path / "memory", device="windows-a", scope="project", files={"MEMORY.md": b"other"}, snapshot_id=manifest["snapshot_id"])
    target = tmp_path / "empty"
    changes = restore_snapshot(tmp_path / "memory", loaded, target)
    assert changes[target / "MEMORY.md"] == b"fact"
    assert (tmp_path / "memory" / "heads" / "windows-a" / "project.json").exists()


def test_missing_baseline_recovers_confirmed_snapshot_without_inventing_deletion(tmp_path, monkeypatch):
    from scripts import sync as sync_script

    monkeypatch.setattr(sync_script, "ROOT", tmp_path / "config-source")
    memory_repo = tmp_path / "memory"
    source = tmp_path / "native"
    source.mkdir()
    manifest = create_snapshot(memory_repo, device="windows-a", scope="project", project_id="project", files={"MEMORY.md": b"fact"})
    mark_head_confirmed(memory_repo, "windows-a", "project")
    config = {
        "device": "windows-a",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(memory_repo),
        "memories": [{"id": "project", "path": str(source)}],
    }
    changes = sync_script.plan(config, "memory")
    sync_script.transaction(changes, tmp_path / "state/backups", state_root=tmp_path / "state")
    assert (source / "MEMORY.md").read_bytes() == b"fact"
    assert (memory_repo / "claude/project/MEMORY.md").read_bytes() == b"fact"


def test_finish_publishes_only_after_code_and_memory_confirmation(tmp_path, monkeypatch):
    from scripts import sync as sync_script

    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(project)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "test@example.invalid"], check=True)
    (project / "README.md").write_text("code")
    subprocess.run(["git", "-C", str(project), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "-m", "initial"], check=True, capture_output=True)
    remote = tmp_path / "project.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(project), "push", "-u", "origin", "main"], check=True, capture_output=True)

    # Use a clean, confirmed ai-config checkout so this test exercises the
    # successful handoff path independently of the working repository.
    config_source = tmp_path / "config-source"
    shutil.copytree(Path(sync_script.ROOT) / "common", config_source / "common")
    (config_source / "codex").mkdir(parents=True)
    (config_source / "claude").mkdir(parents=True)
    shutil.copy2(Path(sync_script.ROOT) / "codex/config.toml", config_source / "codex/config.toml")
    shutil.copy2(Path(sync_script.ROOT) / "claude/settings.shared.json", config_source / "claude/settings.shared.json")
    subprocess.run(["git", "init", "-b", "main", str(config_source)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(config_source), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(config_source), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(config_source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(config_source), "commit", "-m", "initial"], check=True, capture_output=True)
    config_remote = tmp_path / "config.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(config_remote)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(config_source), "remote", "add", "origin", str(config_remote)], check=True)
    subprocess.run(["git", "-C", str(config_source), "push", "-u", "origin", "main"], check=True, capture_output=True)
    monkeypatch.setattr(sync_script, "ROOT", config_source)

    memory_source = tmp_path / "native-memory"
    memory_source.mkdir()
    (memory_source / "MEMORY.md").write_text("portable fact")
    memory_repo = tmp_path / "memory"
    subprocess.run(["git", "init", "-b", "main", str(memory_repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(memory_repo), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(memory_repo), "config", "user.email", "test@example.invalid"], check=True)
    memory_remote = tmp_path / "memory.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(memory_remote)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(memory_repo), "remote", "add", "origin", str(memory_remote)], check=True)
    handoff = tmp_path / "handoff.md"
    handoff.write_text("""# Handoff\n\n## Goal\nkeep context\n## Acceptance criteria\nread it\n## Completed\nsource\n## Remaining\nnone\n## Decisions\nfile-level\n## Blockers\nnone\n## Next step\ncontinue\n## Tests\npass\n## Risks\nnone\n""")
    config = {
        "device": "windows-a",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(memory_repo),
        "memories": [{"id": "project", "path": str(memory_source)}],
        "projects": {"project": str(project)},
    }
    payload = sync_script._run_finish(config, "project", handoff)
    assert payload["status"] == "uploaded"
    assert payload["transport"] == "uploaded"
    assert json.loads((memory_repo / "heads/windows-a/project.json").read_text())["status"] == "uploaded"
    report = sync_script.start_report(memory_repo, "project", payload["handoff_id"], project, current_config=sync_script._config_facts())
    assert report["ready"] is True
    changed_config = sync_script._config_facts()
    changed_config["codex_keys"] = []
    mismatched_config = sync_script.start_report(memory_repo, "project", payload["handoff_id"], project, current_config=changed_config)
    assert mismatched_config["ready"] is False
    assert mismatched_config["checks"]["config_matches"] is False
    (memory_repo / "handoffs/project" / f"{payload['handoff_id']}.md").write_text("tampered")
    tampered = sync_script.start_report(memory_repo, "project", payload["handoff_id"], project, current_config=sync_script._config_facts())
    assert tampered["ready"] is False
    assert tampered["checks"]["handoff_document_hash"] is False


def test_configuration_facts_mark_dirty_repository_incomplete(tmp_path):
    from sync_core.handoff import configuration_facts

    root = tmp_path / "config-source"
    for relative in [
        "common/instructions.md", "common/principles.md", "common/engineering.md", "common/python.md",
        "common/langgraph.md", "common/rag.md", "common/security.md", "codex/config.toml", "claude/settings.shared.json",
    ]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative)
    subprocess.run(["git", "init", "-b", "main", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "initial"], check=True, capture_output=True)
    remote = tmp_path / "config.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(root), "push", "-u", "origin", "main"], check=True, capture_output=True)
    clean = configuration_facts(root, codex_keys=("web_search",), claude_keys=("autoMemoryEnabled",))
    assert clean["ready"] is True
    (root / "common/principles.md").write_text("changed")
    dirty = configuration_facts(root, codex_keys=("web_search",), claude_keys=("autoMemoryEnabled",))
    assert dirty["ready"] is False
    assert "common/principles.md" in dirty["dirty_files"]
    assert dirty["version"] != clean["version"]


def test_inventory_exposes_unmapped_agent_candidates_and_versions(tmp_path):
    from sync_core.config import DeviceConfig
    from sync_core.inventory import discover

    claude_root = tmp_path / "claude"
    (claude_root / "agents").mkdir(parents=True)
    (claude_root / "agents/researcher.md").write_text("agent notes")
    codex_root = tmp_path / "codex"
    (codex_root / "memories").mkdir(parents=True)
    (codex_root / "memories/export.md").write_text("codex export")
    raw = {
        "device": "windows-a",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory"),
        "claude": str(claude_root),
        "codex": str(codex_root),
        "tool_versions": {"claude": "test-1", "codex": "test-2"},
        "memories": [],
    }
    report = discover(DeviceConfig(raw))
    by_id = {item["source_id"]: item for item in report["sources"]}
    assert by_id["claude-candidate:agents"]["status"] == "pending_mapping"
    assert by_id["claude-candidate:agents"]["version"] == "test-1"
    assert by_id["codex-candidate:memories"]["status"] == "pending_mapping"
    assert by_id["codex-candidate:memories"]["version"] == "test-2"


def test_handoff_template_and_snapshot_identity_are_rejected(tmp_path):
    from sync_core.handoff import save_handoff, validate_handoff

    missing = validate_handoff("""# 工作交接

## 使用者目標
<!-- 由当前助手或使用者填写。 -->

## 驗收條件

## 已完成內容
TODO
""")
    assert {"goal", "acceptance", "completed", "remaining", "decisions", "blockers", "next_step", "tests", "risks"}.issubset(missing)
    memory_root = tmp_path / "memory"
    wrong = create_snapshot(memory_root, device="windows-a", scope="other", project_id="other", files={"MEMORY.md": b"other"})
    handoff = """# Handoff

## Goal
goal
## Acceptance criteria
acceptance
## Completed
completed
## Remaining
none
## Decisions
decision
## Blockers
none
## Next step
next
## Tests
pass
## Risks
none
"""
    with pytest.raises(ValueError, match="does not match"):
        save_handoff(memory_root, project_id="project", text=handoff, project_root=tmp_path / "project", memory_snapshot=wrong["snapshot_id"], config_version="config-v1")


def test_quick_setup_detects_and_applies_only_shareable_configuration(tmp_path, monkeypatch):
    from scripts import sync as sync_script

    source_root = tmp_path / "config-source"
    for name in ("instructions", "principles", "engineering", "python", "langgraph", "rag", "security"):
        path = source_root / "common" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
    (source_root / "codex").mkdir()
    (source_root / "claude").mkdir()
    (source_root / "codex/config.toml").write_text('approval_policy = "on-request"\n')
    (source_root / "claude/settings.shared.json").write_text('{"autoMemoryEnabled": true}\n')
    monkeypatch.setattr(sync_script, "ROOT", source_root)
    local = tmp_path / "device.json"
    config = {
        "device": "windows-quick",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory"),
        "codex": str(tmp_path / "codex-home"),
        "claude": str(tmp_path / "claude-home"),
        "codex_keys": [],
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "tool_versions": {},
        "additional_sources": [],
        "codex_memory": str(tmp_path / "codex-home/memories"),
        "memories": [],
        "projects": {},
    }
    preview = sync_script._quick_setup(config, local, apply=False, generated=True)
    assert preview["status"] == "preview"
    assert preview["ready"] is False
    assert preview["config_created"] is True
    assert not local.exists()
    applied = sync_script._quick_setup(config, local, apply=True, generated=True)
    assert applied["status"] == "ready"
    assert applied["ready"] is True
    assert local.exists()
    assert (tmp_path / "codex-home/AGENTS.md").exists()
    assert (tmp_path / "claude-home/CLAUDE.md").exists()
    assert not (tmp_path / "codex-home/config.toml").exists()
    assert not (tmp_path / "claude-home/settings.json").exists()


def _start_fixture(tmp_path, *, local_text: str, remote_text: str | None, with_parent: bool = True, remote_extra: dict[str, bytes] | None = None):
    from scripts import sync as sync_script

    memory_repo = tmp_path / "memory"
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "native-memory"
    source.mkdir()
    (source / "MEMORY.md").write_text(local_text)
    parent_id = None
    if with_parent:
        parent = create_snapshot(memory_repo, device="windows-a", scope="project", project_id="project", files={"MEMORY.md": b"base"})
        mark_head_confirmed(memory_repo, "windows-a", "project")
        parent_id = parent["snapshot_id"]
    remote_files = {} if remote_text is None else {"MEMORY.md": remote_text.encode("utf-8")}
    remote_files.update(remote_extra or {})
    handoff = create_snapshot(
        memory_repo,
        device="windows-a",
        scope="project",
        project_id="project",
        files=remote_files,
        parent_snapshot=parent_id,
    )
    mark_head_confirmed(memory_repo, "windows-a", "project")
    config = {
        "device": "windows-b",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(memory_repo),
        "memories": [{"id": "project", "path": str(source)}],
        "projects": {"project": str(project)},
    }
    if with_parent:
        state = Path(config["state_dir"])
        state.mkdir(parents=True, exist_ok=True)
        (state / "memory-project.json").write_text(json.dumps({"schema_version": 1, "files": {"MEMORY.md": digest(b"base")}}))
    return sync_script, config, source, handoff["snapshot_id"], memory_repo


def test_start_merges_local_and_remote_then_memory_is_stable(tmp_path, monkeypatch):
    sync_script, config, source, snapshot_id, memory_repo = _start_fixture(
        tmp_path, local_text="base", remote_text="remote", remote_extra={"remote.md": b"remote addition"}
    )
    monkeypatch.setattr(sync_script, "ROOT", tmp_path / "config-source")
    (source / "local.md").write_text("local addition")
    report = {"ready": True, "memory_snapshot": snapshot_id}
    plan = sync_script._start_plan(config, "project", report, True, Path(config["state_dir"]))
    assert (source / "MEMORY.md").read_text() == "remote"
    assert (source / "local.md").read_text() == "local addition"
    assert (source / "remote.md").read_text() == "remote addition"
    assert (memory_repo / "claude/project/local.md").read_text() == "local addition"
    assert plan.metadata["pre_start_snapshot"]
    assert not sync_script.plan(config, "memory")


@pytest.mark.parametrize(
    ("local_text", "remote_text", "with_parent"),
    [("local", "remote", True), ("changed", None, True), ("local", "remote", False)],
)
def test_start_conflict_or_missing_baseline_preserves_local_and_snapshot(tmp_path, local_text, remote_text, with_parent):
    sync_script, config, source, snapshot_id, memory_repo = _start_fixture(
        tmp_path, local_text=local_text, remote_text=remote_text, with_parent=with_parent
    )
    from scripts.sync import SyncCommandError

    with pytest.raises(SyncCommandError) as error:
        sync_script._start_plan(config, "project", {"ready": True, "memory_snapshot": snapshot_id}, True, Path(config["state_dir"]))
    assert error.value.code == 4
    assert (source / "MEMORY.md").read_text() == local_text
    preserved = list((memory_repo / "snapshots/windows-b").glob("*.json"))
    assert preserved


def test_cli_missing_handoff_is_incomplete_exit(tmp_path):
    config = tmp_path / "device.json"
    config.write_text(json.dumps({
        "device": "windows-b",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory"),
        "projects": {"project": str(tmp_path / "project")},
    }))
    script = Path(__file__).parents[1] / "scripts/sync.py"
    result = subprocess.run(
        ["python", str(script), "start", "--local", str(config), "--project", "project", "--handoff-id", "missing"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2


def test_finish_cli_returns_incomplete_for_unconfirmed_config(tmp_path):
    external = Path(tempfile.mkdtemp(prefix="ai-sync-finish-", dir=str(Path(__file__).resolve().parents[2])))
    source = external / "native-memory"
    source.mkdir()
    (source / "MEMORY.md").write_text("portable fact")
    project = external / "project"
    project.mkdir()
    handoff = external / "handoff.md"
    handoff.write_text("""# Handoff

## Goal
keep context
## Acceptance criteria
read it
## Completed
source
## Remaining
none
## Decisions
file-level
## Blockers
none
## Next step
continue
## Tests
pass
## Risks
none
""")
    config = external / "device.json"
    config.write_text(json.dumps({
        "device": "windows-a",
        "state_dir": str(external / "state"),
        "memory_repo": str(external / "memory"),
        "memories": [{"id": "project", "path": str(source)}],
        "projects": {"project": str(project)},
    }))
    script = Path(__file__).parents[1] / "scripts/sync.py"
    result = subprocess.run(
        ["python", str(script), "finish", "--apply", "--local", str(config), "--project", "project", "--handoff", str(handoff)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert '"status": "incomplete"' in result.stdout
    shutil.rmtree(external, ignore_errors=True)
