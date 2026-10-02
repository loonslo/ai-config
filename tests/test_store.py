"""An independent configuration store, opted into with ``setup --store``."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sync_core import agents, store

ROOT = Path(__file__).resolve().parents[1]


def test_the_starter_template_is_a_complete_store():
    assert store.is_store(store.TEMPLATE)
    # The example agents.toml is comments only: no choice until the user makes one.
    assert agents.store_preferences(store.TEMPLATE) == {}


def test_plans_never_take_over_an_unrelated_directory(tmp_path):
    assert store.plan_store(tmp_path / "new", remote=None)["action"] == "create"
    assert store.plan_store(tmp_path / "new", remote="https://example.invalid/x.git")["action"] == "clone"
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(store.StoreError, match="不是 ai-config 配置库"):
        store.plan_store(occupied, remote=None)


def test_a_created_store_is_used_again_without_initializing_git(tmp_path, monkeypatch):
    target = tmp_path / "store"
    def no_git(*args, **kwargs):
        raise AssertionError("creating an offline store must not call Git")
    monkeypatch.setattr(store, "_git", no_git)
    store.execute(store.plan_store(target, remote=None))
    assert store.is_store(target)
    assert not (target / ".git").exists()
    assert store.plan_store(target, remote=None)["action"] == "use"


def test_joining_clones_an_existing_store(tmp_path):
    first = tmp_path / "first"
    store.execute(store.plan_store(first, remote=None))
    initialized = store._git(["init", "--quiet"], cwd=first)
    assert initialized.returncode == 0, initialized.stderr
    staged = store._git(["add", "."], cwd=first)
    assert staged.returncode == 0, staged.stderr
    committed = store._git([
        "-c", "user.email=ai-config@example.invalid",
        "-c", "user.name=ai-config tests",
        "commit", "--quiet", "-m", "test store clone",
    ], cwd=first)
    assert committed.returncode == 0, committed.stderr
    second = tmp_path / "second"
    store.execute(store.plan_store(second, remote=str(first)))
    assert store.is_store(second)


def _setup(home: Path, local: Path | None, *args: str, path: Path | None = None) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if key not in {"CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "AI_CONFIG_HOME"}}
    env.update({
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "PYTHONIOENCODING": "utf-8",
    })
    if path is not None:
        env["PATH"] = str(path)
    local_args = ["--local", str(local)] if local is not None else []
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync.py"), "setup", *local_args, *args],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(local.parent if local else home),
    )


def test_setup_with_a_store_records_it_and_preview_writes_nothing(tmp_path):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".workbuddy").mkdir(parents=True)
    local = tmp_path / "device.json"
    target = tmp_path / "my-store"

    preview = _setup(home, local, "--store", str(target), "--json")
    assert preview.returncode == 0, preview.stderr
    assert json.loads(preview.stdout)["store"]["action"] == "create"
    assert not target.exists() and not local.exists()

    applied = _setup(home, local, "--store", str(target), "--state-dir", str(tmp_path / "state"), "--apply")
    assert applied.returncode == 0, applied.stdout + applied.stderr
    raw = json.loads(local.read_text(encoding="utf-8"))
    assert Path(raw["config_repo"]) == target.resolve()
    assert "workbuddy" in raw["agents"]
    assert store.is_store(target)


def test_default_setup_uses_user_data_root_and_does_not_need_git(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".codex").mkdir()
    no_git = tmp_path / "no-git-bin"
    no_git.mkdir()

    preview = _setup(home, None, "--json", path=no_git)
    report = json.loads(preview.stdout)
    assert preview.returncode == 0, preview.stderr
    assert report["ready"] is True
    assert report["git"] is False
    assert report["store"]["action"] == "create"
    assert not (home / ".ai-sync").exists()

    applied = _setup(home, None, "--apply", "--json", path=no_git)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    config_path = home / ".ai-sync" / "device.json"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert Path(raw["config_repo"]) == (home / ".ai-sync" / "store")
    assert Path(raw["state_dir"]) == (home / ".ai-sync" / "state")
    assert store.is_store(home / ".ai-sync" / "store")
    assert not (home / ".ai-sync" / "store" / ".git").exists()
