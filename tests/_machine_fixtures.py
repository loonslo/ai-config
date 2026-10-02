"""Synthetic migration homes; all paths are below the caller's tmp_path."""
from __future__ import annotations

import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import zipfile

from _agent_homes import SENTINEL, build_home
from sync_core.machine.paths import derive_project_dir


def build_machine_home(home: Path) -> dict[str, Path]:
    decoys = build_home(home, agents=("claude", "codex", "workbuddy", "workbuddy-ai"))
    workspace = home / "workspace"
    project = workspace / "sample-project"
    project.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    native = str(project)
    (home / ".claude.json").write_text(json.dumps({
        "projects": {native: {"hasTrustDialogAccepted": True}, native.replace("\\", "/"): {"hasTrustDialogAccepted": True}},
        "oauthAccount": SENTINEL, "machineID": SENTINEL, "mcpServers": {"private": SENTINEL},
    }), encoding="utf-8")
    encoded = derive_project_dir(native)
    assert encoded is not None
    memory = home / ".claude" / "projects" / encoded / "memory"
    memory.mkdir(parents=True)
    (memory / "MEMORY.md").write_text("# Safe synthetic memory\n", encoding="utf-8")
    (memory.parent / "synthetic-session.jsonl").write_text(SENTINEL, encoding="utf-8")
    local = project / ".claude" / "settings.local.json"
    local.parent.mkdir(parents=True)
    local.write_text('{"permissions":{"allow":["Read"]}}\n', encoding="utf-8")
    (home / ".codex" / "config.toml").write_text(
        'model_reasoning_effort = "high"\n[shell_environment_policy.set]\nTEST_SECRET = "' + SENTINEL + '"\n'
        + "[projects.'" + native.replace("\\", "/").lower() + "']\ntrust_level = \"trusted\"\n", encoding="utf-8")
    (home / ".codex" / "skills" / "diary" / "icon.bin").write_bytes(b"\x00\xff" + SENTINEL.encode())
    db = home / ".codex" / "state_5.sqlite"
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.executescript("CREATE TABLE projects(id TEXT, name TEXT); CREATE TABLE project_roots(project_id TEXT, path TEXT); CREATE TABLE threads(id TEXT, cwd TEXT);")
        connection.execute("INSERT INTO projects VALUES (?, ?)", ("p1", "sample-project"))
        connection.execute("INSERT INTO project_roots VALUES (?, ?)", ("p1", native))
        connection.execute("INSERT INTO threads VALUES (?, ?)", ("t1", native))
    for agent in ("workbuddy", "workbuddy-ai"):
        root = project / f".{agent}" / "memory"
        root.mkdir(parents=True)
        (root / "note.md").write_text("# project memory\n", encoding="utf-8")
        (project / f".{agent}" / "skills").mkdir()
        (project / f".{agent}" / "skills" / ".old_migration.json").write_text(SENTINEL, encoding="utf-8")
    return {"home": home, "workspace": workspace, "project": project, "protected": decoys["protected"]}


def assert_no_sentinel(zip_path: Path) -> None:
    marker = SENTINEL.encode()
    assert marker not in zip_path.read_bytes()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            assert marker not in archive.read(info)


def snapshot_tree(root: Path) -> dict[str, tuple[str, bytes | None]]:
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("symlink", str(path.readlink()).encode())
        elif path.is_file():
            snapshot[relative] = ("file", hashlib.sha256(path.read_bytes()).digest())
        elif path.is_dir():
            snapshot[relative] = ("dir", None)
    return snapshot


def assert_tree_unchanged(before: dict[str, tuple[str, bytes | None]], root: Path) -> None:
    assert snapshot_tree(root) == before
