"""User data layout and explicit, backed-up migration of a legacy device file."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sync_core import layout
from sync_core.wizard import plan_device

ROOT = Path(__file__).resolve().parents[1]


def _legacy_config(home: Path) -> dict:
    return plan_device(
        device_id="windows-old",
        state_dir=home / ".ai-sync" / "state",
        memory_repo=home / "ai-memory",
        tools=["codex"],
        scope="rules_only",
        remote_url=None,
        tool_roots={"codex": str(home / ".codex")},
    )


def test_user_paths_share_a_data_root_and_can_be_overridden(tmp_path):
    root = tmp_path / "profile" / ".ai-sync"
    assert layout.data_root(home=tmp_path / "profile", environ={}) == root
    assert layout.default_device_config_path(home=tmp_path / "profile", environ={}) == root / "device.json"
    assert layout.default_state_path(home=tmp_path / "profile", environ={}) == root / "state"
    assert layout.default_store_path(home=tmp_path / "profile", environ={}) == root / "store"

    override = tmp_path / "managed" / "ai-data"
    assert layout.data_root(environ={"AI_CONFIG_HOME": str(override)}) == override
    with pytest.raises(layout.LayoutError, match="absolute"):
        layout.data_root(environ={"AI_CONFIG_HOME": "relative/path"})


def test_legacy_import_preview_writes_nothing_then_copies_and_keeps_a_backup(tmp_path):
    source = tmp_path / "old-checkout" / "device.json"
    source.parent.mkdir()
    original = json.dumps(_legacy_config(tmp_path / "profile"), ensure_ascii=False, indent=2).encode("utf-8")
    source.write_bytes(original)
    target = tmp_path / "profile" / ".ai-sync" / "device.json"

    plan = layout.plan_device_config_import(source, target)
    assert plan.action == "copy"
    assert not target.parent.exists()
    assert not plan.backup.exists()

    report = layout.import_device_config(plan)
    assert report["status"] == "imported"
    assert target.read_bytes() == original
    assert plan.backup.read_bytes() == original
    assert source.read_bytes() == original
    assert Path(json.loads(target.read_text(encoding="utf-8"))["state_dir"]) == tmp_path / "profile" / ".ai-sync" / "state"

    assert layout.plan_device_config_import(source, target).action == "already_imported"


def test_legacy_import_refuses_invalid_input_and_conflicting_destination(tmp_path):
    source = tmp_path / "device.json"
    source.write_text("not a device config", encoding="utf-8")
    target = tmp_path / "new" / "device.json"
    with pytest.raises(layout.LayoutError, match="无法读取"):
        layout.plan_device_config_import(source, target)
    assert not target.parent.exists()

    source.write_text(json.dumps(_legacy_config(tmp_path)), encoding="utf-8")
    target.parent.mkdir()
    target.write_text("different config", encoding="utf-8")
    with pytest.raises(layout.LayoutError, match="不会覆盖"):
        layout.plan_device_config_import(source, target)
    assert target.read_text(encoding="utf-8") == "different config"


def test_legacy_import_rechecks_source_after_preview(tmp_path):
    source = tmp_path / "device.json"
    source.write_text(json.dumps(_legacy_config(tmp_path)), encoding="utf-8")
    target = tmp_path / "new" / "device.json"
    plan = layout.plan_device_config_import(source, target)
    source.write_text(json.dumps({**_legacy_config(tmp_path), "device": "windows-updated"}), encoding="utf-8")

    with pytest.raises(layout.LayoutError, match="预览后发生变化"):
        layout.import_device_config(plan)
    assert source.exists()
    assert not target.exists()


def test_cli_import_config_previews_then_backups_and_migrates_without_git(tmp_path):
    home = tmp_path / "profile"
    home.mkdir()
    source_root = tmp_path / "legacy-checkout"
    source_root.mkdir()
    source = source_root / "device.json"
    source.write_text(json.dumps(_legacy_config(home), ensure_ascii=False), encoding="utf-8")
    no_git = tmp_path / "no-git-bin"
    no_git.mkdir()
    env = {
        key: value for key, value in os.environ.items()
        if key not in {"CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "AI_CONFIG_HOME"}
    }
    env.update({
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "PATH": str(no_git),
        "PYTHONIOENCODING": "utf-8",
    })
    command = [sys.executable, str(ROOT / "scripts" / "sync.py"), "import-config", "--source", str(source), "--json"]
    preview = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=env, cwd=source_root)
    target = home / ".ai-sync" / "device.json"
    assert preview.returncode == 0, preview.stderr
    preview_data = json.loads(preview.stdout)
    assert preview_data["status"] == "preview"
    assert Path(preview_data["target"]) == target
    assert not target.exists()
    assert not source.with_name("device.json.bak-ai-config").exists()

    applied = subprocess.run([*command[:-1], "--apply", "--json"], capture_output=True, text=True, encoding="utf-8", env=env, cwd=source_root)
    assert applied.returncode == 0, applied.stderr
    result = json.loads(applied.stdout)
    assert result["status"] == "imported"
    assert target.exists()
    assert source.exists()
    assert Path(result["backup"]).read_bytes() == source.read_bytes()


def test_default_setup_stops_and_explains_how_to_import_legacy_config(tmp_path):
    home = tmp_path / "profile"
    home.mkdir()
    legacy = home / "device.json"
    legacy.write_text(json.dumps(_legacy_config(home)), encoding="utf-8")
    env = {
        key: value for key, value in os.environ.items()
        if key not in {"CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "AI_CONFIG_HOME"}
    }
    env.update({
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "PYTHONIOENCODING": "utf-8",
    })
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync.py"), "setup", "--apply"],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=home,
    )
    assert result.returncode == 2
    assert "import-config --source" in result.stderr
    assert legacy.exists()
    assert not (home / ".ai-sync").exists()
