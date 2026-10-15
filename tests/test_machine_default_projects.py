from dataclasses import replace
import json
from pathlib import Path
import subprocess

from sync_core.application.machine_protocol import MachineProtocol
from sync_core.machine.backup import prepare_backup
from sync_core.machine.collect_projects import default_projects
from sync_core.machine.config import load_config
from sync_core.machine.paths import derive_project_dir


def test_detect_defaults_to_all_existing_registrations_and_carries_their_memories(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".codex").mkdir()
    projects = [tmp_path / "workspace" / name for name in ("one", "two")]
    worktree = tmp_path / "workspace" / "one" / ".claude" / "worktrees" / "temporary"
    scratch = tmp_path / "scratch-workspaces" / "scratch"
    for p in (*projects, worktree, scratch):
        p.mkdir(parents=True, exist_ok=True)
    for p in projects:
        subprocess.run(["git", "init", "-q", str(p)], check=True)
    dead = tmp_path / "dead"
    (home / ".claude.json").write_text(json.dumps({"projects": {str(p): {} for p in (projects[0], worktree, scratch, dead)}}), encoding="utf-8")
    (home / ".codex" / "config.toml").write_text("[projects." + json.dumps(projects[1].as_posix()) + "]\ntrust_level = 'trusted'\n", encoding="utf-8")
    for p in projects:
        memory = home / ".claude" / "projects" / derive_project_dir(str(p)) / "memory" / "nested"
        memory.mkdir(parents=True)
        (memory / "note.md").write_bytes(p.name.encode())
    config = load_config(tmp_path / "missing.json", home=home)
    found = default_projects(home=home, config=config, environ={}, os_name="windows")
    assert {Path(p) for p in found} == set(projects)
    protocol = MachineProtocol(tmp_path / "device.json", home=home, environ={})
    detected = protocol._invoke("machine_detect", {}, apply=False).data
    assert {Path(p) for p in detected["projects"]} == set(projects)
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr("sync_core.machine.procs.process_names", lambda: [])
    plan = prepare_backup(home=home, config=replace(config, core_projects=tuple(Path(p) for p in found)),
                          out=out, environ={}, agents=frozenset({"claude", "codex"}),
                          software={"versions": {}}, git_keys=[])
    entries = [e for e in plan.writer.entries if e["kind"] == "memory"]
    assert len(entries) == 2
    assert {plan.writer._files[e["archive_path"]] for e in entries} == {b"one", b"two"}
