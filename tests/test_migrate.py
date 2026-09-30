"""``migrate`` and ``detach`` in sandbox homes.

The flagship property: an agent migrated, synchronized and then detached with
``--restore-original`` is byte-for-byte what it was before ai-config touched
it.  Along the way duplicates are removed only after a backup, unique rules are
never touched without an explicit choice, secrets block, repeated runs change
nothing, and every step can be undone.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sync_core import agents, config_sync, migrate
from sync_core.config import DeviceConfig, load as load_config
from sync_core.restore import restore
from sync_core.transaction import transaction
from sync_core.utils import json_bytes

import scripts.sync as sync_script

from _agent_homes import HAND_WRITTEN_RULES, SENTINEL, build_home, device_raw, write_store

ROOT = Path(__file__).resolve().parents[1]

USER_SECTION = "## 我的本地约定\n\n- 提交前先跑 ruff。\n"


def _host(home: Path) -> agents.HostEnv:
    return agents.HostEnv.for_home(home, system="windows", environ={}, which=lambda name: None)


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {path.relative_to(root).as_posix(): (path.read_bytes() if path.is_file() else None) for path in sorted(root.rglob("*"))}


class Sandbox:
    def __init__(self, tmp_path: Path, *, agents_in_home=("codex",), legacy=("codex",), declared=None, store_text=HAND_WRITTEN_RULES):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        build_home(self.home, agents=agents_in_home)
        self.store = write_store(tmp_path / "store", instructions=store_text)
        self.local = tmp_path / "device.json"
        legacy_roots = {name: self.home / f".{name}" for name in legacy}
        declared_roots = {name: {"root": self.home / f".{name}"} for name in (declared or ())}
        raw = device_raw(tmp_path, self.store, legacy=legacy_roots, agents=declared_roots or None)
        self.local.write_bytes(json_bytes(raw))

    @property
    def raw(self) -> dict:
        return load_config(self.local).raw

    @property
    def state(self) -> Path:
        return self.tmp / "state"

    def plan(self) -> migrate.MigrationPlan:
        return migrate.plan_migration(self.raw, local=self.local, host=_host(self.home), store_root=self.store, state_dir=self.state)

    def apply(self, *, item: str | None = None, choice: str | None = None) -> dict:
        plan = self.plan()
        selections = migrate.select(plan, item=item, choice=choice)
        changes, summary = migrate.build_changes(plan, selections, state_dir=self.state)
        if changes:
            transaction(changes, self.state / "backups", state_root=self.state)
        return summary

    def sync(self) -> dict:
        return config_sync.sync(DeviceConfig(self.raw, self.local), apply=True)

    def detach(self, instance: str, *, restore_original: bool) -> dict:
        changes, report = migrate.plan_detach(self.raw, local=self.local, instance_id=instance, state_dir=self.state, restore_original=restore_original)
        transaction(changes, self.state / "backups", state_root=self.state)
        migrate.remove_empty_dirs(report.get("remove_dirs"))
        return report


def _item(plan: migrate.MigrationPlan, instance: str, kind: str) -> migrate.Item:
    return next(item for item in plan.items if item.instance == instance and item.kind == kind)


# --------------------------------------------------------------------------
# sections and block helpers
# --------------------------------------------------------------------------

def test_sections_split_on_headings_and_keep_every_byte():
    text = "intro\n\n# A\n- a\n\n## B\r\n- b\r\n"
    sections = migrate.split_sections(text)
    assert [section.heading for section in sections] == [None, "# A", "## B"]
    assert "".join(section.raw for section in sections) == text
    assert (sections[2].start, sections[2].end) == (6, 7)


def test_strip_block_undoes_what_sync_appended():
    original = b"# mine\r\n"
    synced = original + b"\n\n" + b"<!-- ai-config:begin -->\nx\n<!-- ai-config:end -->" + b"\n"
    assert migrate.strip_block(synced) == original
    assert migrate.strip_block(b"<!-- ai-config:begin -->\nx\n<!-- ai-config:end -->\n") is None


# --------------------------------------------------------------------------
# migrate
# --------------------------------------------------------------------------

def test_a_duplicate_copy_is_removed_by_default_and_undo_brings_it_back(tmp_path):
    box = Sandbox(tmp_path)
    agents_md = box.home / ".codex" / "AGENTS.md"
    box.sync()  # the hand-written copy and the managed block now coexist
    before = agents_md.read_bytes()
    plan = box.plan()
    duplicates = [item for item in plan.items if item.kind == migrate.KIND_DUPLICATE]
    assert duplicates and all(item.default == "remove" for item in duplicates)
    box.apply()
    after = agents_md.read_bytes()
    assert after.startswith(b"<!-- ai-config:begin -->")
    assert b"# Developer Profile\n\n## Coding Style" not in after.split(b"<!-- ai-config:end -->")[1]
    # The block itself is untouched: the device still verifies, with nothing to write.
    report = box.sync()
    assert report["verified"] is True and report["changes"] == 0
    from sync_core.restore import recent_operations

    migration = next(item for item in recent_operations(box.state) if item["operation"] == "migrate")
    restore(box.state, operation_id=migration["operation_id"], apply=True)
    assert agents_md.read_bytes() == before


def test_unique_rules_are_never_touched_without_a_choice(tmp_path):
    box = Sandbox(tmp_path)
    agents_md = box.home / ".codex" / "AGENTS.md"
    agents_md.write_bytes((HAND_WRITTEN_RULES + "\n" + USER_SECTION).encode("utf-8"))
    plan = box.plan()
    unique = _item(plan, "codex", migrate.KIND_UNIQUE)
    assert unique.default is None and [line.text for line in unique.unique] == ["## 我的本地约定", "- 提交前先跑 ruff。"]
    assert unique.id not in migrate.select(plan, item=None, choice=None)
    box.apply()
    assert USER_SECTION.encode("utf-8") in agents_md.read_bytes()


def test_adopting_moves_unique_lines_into_the_store_verbatim(tmp_path):
    box = Sandbox(tmp_path)
    agents_md = box.home / ".codex" / "AGENTS.md"
    agents_md.write_bytes(USER_SECTION.encode("utf-8"))
    unique = _item(box.plan(), "codex", migrate.KIND_UNIQUE)
    summary = box.apply(item=unique.id, choice="adopt")
    assert summary["adopted"] == [unique.id]
    imported = (box.store / "common" / "imported.md").read_text(encoding="utf-8")
    assert "- 提交前先跑 ruff。" in imported and "迁入：Codex · AGENTS.md" in imported
    assert not agents_md.exists()  # nothing of the user's was left in the file
    body = sync_script._rules_body(box.raw).decode("utf-8")
    assert "- 提交前先跑 ruff。" in body
    assert [item for item in box.plan().items if item.instance == "codex"] == []


def test_a_rule_copied_into_several_agents_is_recognized_as_one(tmp_path):
    box = Sandbox(tmp_path, agents_in_home=("codex", "claude"), legacy=("codex", "claude"))
    for path in (box.home / ".codex" / "AGENTS.md", box.home / ".claude" / "CLAUDE.md"):
        path.write_bytes(USER_SECTION.encode("utf-8"))
    plan = box.plan()
    codex = _item(plan, "codex", migrate.KIND_UNIQUE)
    assert codex.shared_with == ("claude",)
    box.apply(item=codex.id, choice="adopt")
    # Once adopted, the Claude copy is a plain duplicate and goes by default.
    claude = _item(box.plan(), "claude", migrate.KIND_DUPLICATE)
    assert claude.default == "remove"
    box.apply()
    imported = (box.store / "common" / "imported.md").read_text(encoding="utf-8")
    assert imported.count("- 提交前先跑 ruff。") == 1


def test_keep_is_remembered_and_the_file_is_left_alone(tmp_path):
    box = Sandbox(tmp_path)
    agents_md = box.home / ".codex" / "AGENTS.md"
    agents_md.write_bytes(USER_SECTION.encode("utf-8"))
    unique = _item(box.plan(), "codex", migrate.KIND_UNIQUE)
    box.apply(item=unique.id, choice="keep")
    assert agents_md.read_bytes() == USER_SECTION.encode("utf-8")
    assert [item for item in box.plan().items if item.instance == "codex"] == []


def test_choices_are_checked_per_item(tmp_path):
    box = Sandbox(tmp_path)
    plan = box.plan()
    duplicate = _item(plan, "codex", migrate.KIND_DUPLICATE)
    with pytest.raises(migrate.MigrationError, match="不能选择"):
        migrate.select(plan, item=duplicate.id, choice="adopt")
    with pytest.raises(migrate.MigrationError, match="--item"):
        migrate.select(plan, item=None, choice="remove")
    with pytest.raises(migrate.MigrationError, match="没有找到"):
        migrate.select(plan, item="nope", choice="remove")


def test_a_rules_file_with_a_secret_is_blocked_and_never_printed(tmp_path):
    box = Sandbox(tmp_path)
    key_name = "API" + "_KEY"
    (box.home / ".codex" / "AGENTS.md").write_bytes(f"{key_name}={SENTINEL}\n".encode("ascii"))
    plan = box.plan()
    assert plan.blocked == [{"instance": "codex", "path": "AGENTS.md", "reason": "blocked_secret"}]
    assert [item for item in plan.items if item.instance == "codex"] == []
    assert SENTINEL not in migrate.render_plan(plan)


def test_found_agents_are_registered_with_a_backup_of_the_device_file(tmp_path):
    box = Sandbox(tmp_path, agents_in_home=("codex", "workbuddy", "workbuddy-ai"))
    before = box.local.read_bytes()
    plan = box.plan()
    registers = sorted(item.instance for item in plan.items if item.kind == migrate.KIND_REGISTER)
    assert registers == ["workbuddy", "workbuddy-ai"]
    skip = _item(plan, "workbuddy-ai", migrate.KIND_REGISTER)
    box.apply(item=skip.id, choice="skip")
    box.apply()
    assert set(box.raw["agents"]) == {"workbuddy"}
    # workbuddy-ai stays unregistered and is not proposed again.
    assert [item.instance for item in box.plan().items if item.kind == migrate.KIND_REGISTER] == []
    backups = list((box.state / "backups").rglob("*"))
    assert any(path.is_file() and path.read_bytes() == before for path in backups)


def test_a_second_run_changes_nothing(tmp_path):
    box = Sandbox(tmp_path, agents_in_home=("codex", "workbuddy"))
    box.apply()
    snapshot = _snapshot(box.tmp)
    plan = box.plan()
    changes, _ = migrate.build_changes(plan, migrate.select(plan, item=None, choice=None), state_dir=box.state)
    assert len(changes) == 0
    assert _snapshot(box.tmp) == snapshot


def test_a_change_after_the_preview_invalidates_the_batch(tmp_path):
    box = Sandbox(tmp_path)
    plan = box.plan()
    changes, _ = migrate.build_changes(plan, migrate.select(plan, item=None, choice=None), state_dir=box.state)
    agents_md = box.home / ".codex" / "AGENTS.md"
    agents_md.write_bytes(agents_md.read_bytes() + b"\n- edited meanwhile\n")
    with pytest.raises(ValueError, match="invalidated"):
        transaction(changes, box.state / "backups", state_root=box.state)
    assert b"edited meanwhile" in agents_md.read_bytes()


# --------------------------------------------------------------------------
# detach
# --------------------------------------------------------------------------

def test_detach_removes_only_what_ai_config_wrote(tmp_path):
    box = Sandbox(tmp_path, agents_in_home=("workbuddy",), legacy=(), declared=("workbuddy",))
    manual = box.home / ".workbuddy" / "AGENTS.md"
    manual.write_bytes("# 我的工作手册\n".encode("utf-8"))
    box.sync()
    assert b"ai-config:begin" in manual.read_bytes()
    report = box.detach("workbuddy", restore_original=False)
    assert report["files"][0]["action"] == "remove_block"
    assert manual.read_bytes() == "# 我的工作手册\n".encode("utf-8")
    assert "agents" not in box.raw


def test_migrate_sync_detach_restores_the_home_byte_for_byte(tmp_path):
    box = Sandbox(tmp_path, agents_in_home=("codebuddy", "workbuddy"), legacy=(), declared=())
    (box.home / ".codebuddy" / "CODEBUDDY.md").write_bytes(HAND_WRITTEN_RULES.encode("utf-8"))
    (box.home / ".workbuddy" / "AGENTS.md").write_bytes((HAND_WRITTEN_RULES + "\n" + USER_SECTION).encode("utf-8"))
    original = _snapshot(box.home)

    box.apply()  # register both, remove the fully duplicated sections
    unique = _item(box.plan(), "workbuddy", migrate.KIND_UNIQUE)
    box.apply(item=unique.id, choice="adopt")
    assert box.sync()["verified"] is True
    assert (box.home / ".codebuddy" / "rules" / "ai-config.md").exists()
    assert not (box.home / ".codebuddy" / "CODEBUDDY.md").exists()

    for instance in ("codebuddy", "workbuddy"):
        report = box.detach(instance, restore_original=True)
        assert report["conflicts"] == []
    assert _snapshot(box.home) == original


def test_restore_original_refuses_to_overwrite_later_edits(tmp_path):
    box = Sandbox(tmp_path, agents_in_home=("codebuddy",), legacy=(), declared=("codebuddy",))
    cb = box.home / ".codebuddy" / "CODEBUDDY.md"
    cb.write_bytes((HAND_WRITTEN_RULES + "\n" + USER_SECTION).encode("utf-8"))
    box.apply()  # removes the duplicated sections, keeps the unique one
    cb.write_bytes(cb.read_bytes() + "- 后来又加的一条\n".encode("utf-8"))
    report = box.detach("codebuddy", restore_original=True)
    assert report["restored"] == []
    assert report["conflicts"] and "又被修改" in report["conflicts"][0]["reason"]
    assert "后来又加的一条" in cb.read_text(encoding="utf-8")


def test_migrate_and_detach_are_listed_by_undo(tmp_path):
    from sync_core.restore import recent_operations

    box = Sandbox(tmp_path)
    box.apply()
    operations = recent_operations(box.state)
    assert operations[0]["operation"] == "migrate"
    assert "迁入" in operations[0]["statement"]


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------

def _run(box: Sandbox, *args: str) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if key not in {"CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME"}}
    env.update({
        "HOME": str(box.home),
        "USERPROFILE": str(box.home),
        "APPDATA": str(box.home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(box.home / "AppData" / "Local"),
        "PYTHONIOENCODING": "utf-8",
    })
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync.py"), *args, "--local", str(box.local)],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(box.tmp),
    )


def test_migrate_preview_command_writes_nothing(tmp_path):
    box = Sandbox(tmp_path, agents_in_home=("codex", "workbuddy"))
    before = _snapshot(box.tmp)
    result = _run(box, "migrate", "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "preview" and report["written"] is False
    assert {item["kind"] for item in report["items"]} >= {"register", "duplicate"}
    assert _snapshot(box.tmp) == before


def test_diff_and_migrate_only_accept_their_own_choices(tmp_path):
    box = Sandbox(tmp_path)
    assert _run(box, "diff", "--choice", "adopt").returncode == 2
    assert _run(box, "migrate", "--item", "1", "--choice", "share").returncode == 2
