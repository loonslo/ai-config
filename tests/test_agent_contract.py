"""One contract, every writable adapter.

Each case builds a sandbox home in the shape the agent really uses, then runs
the same sequence: detect, render, apply, verify, repeat (no change), local
edit (refused), undo, and detach -- after which the home must be byte for byte
what it was before ai-config touched it.  Protected decoys are never read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from sync_core import agents, config_sync, migrate
from sync_core.config import DeviceConfig, validate
from sync_core.load_check import extract_version
from sync_core.restore import recent_operations, restore
from sync_core.transaction import transaction
from sync_core.utils import json_bytes

import scripts.sync as sync_script

from _agent_homes import SENTINEL, ReadTracker, device_raw, write_store


@dataclass(frozen=True)
class Case:
    instance: str
    directory: str
    entry: str
    kind: str
    seed: dict[str, str | None] = field(default_factory=dict)
    decoys: tuple[str, ...] = ()
    legacy: bool = False
    generic: dict[str, str] | None = None


CASES = [
    Case("codex", ".codex", "AGENTS.md", agents.KIND_BLOCK, {"AGENTS.md": "# mine\n"}, ("auth.json", "secrets/token.bin"), legacy=True),
    Case("claude", ".claude", "CLAUDE.md", agents.KIND_BLOCK, {"CLAUDE.md": "# mine\n"}, (".credentials.json",), legacy=True),
    Case("codebuddy", ".codebuddy", "rules/ai-config.md", agents.KIND_FILE, {"settings.json": "{}\n"}, ("models.json", "connectors/default/mcp.json")),
    Case("workbuddy", ".workbuddy", "AGENTS.md", agents.KIND_BLOCK, {"SOUL.md": "persona\n"}, ("keyblob", "security/vault.bin", "app/connector-keys/k.json")),
    Case("workbuddy-ai", ".workbuddy-ai", "AGENTS.md", agents.KIND_BLOCK, {"USER.md": "about me\n"}, ("keyblob",)),
    Case("trae", ".trae", "user_rules/ai-config.md", agents.KIND_FILE, {"user_rules/team.md": "# team\n"}),
    Case("trae-cn", ".trae-cn", "user_rules.md", agents.KIND_BLOCK, {"user_rules.md": "# mine\n"}),
    Case("kiro-steering", ".kiro", "steering/ai-config.md", agents.KIND_FILE, {"steering": None}, generic={"mode": "owned_file", "path": "steering/ai-config.md"}),
    Case("opencode", ".config/opencode", "AGENTS.md", agents.KIND_BLOCK, {"AGENTS.md": "# mine\n"}, generic={"mode": "managed_block", "path": "AGENTS.md"}),
    Case("deep", ".deep", "a/b/ai-config.md", agents.KIND_FILE, {"x.txt": "x\n"}, generic={"mode": "owned_file", "path": "a/b/ai-config.md"}),
]


def _snapshot(root: Path, *, files_only: bool = False) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes() if path.is_file() else None)
        for path in sorted(root.rglob("*"))
        if path.is_file() or not files_only
    }


def _build(tmp_path: Path, case: Case) -> tuple[Path, Path, DeviceConfig, list[Path]]:
    home = tmp_path / "home"
    root = home / case.directory
    root.mkdir(parents=True)
    for relative, text in case.seed.items():
        path = root / relative
        if text is None:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
    decoys = []
    for relative in case.decoys:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"{SENTINEL}\n".encode("ascii"))
        decoys.append(path)
    store = write_store(tmp_path / "store")
    if case.legacy:
        raw = device_raw(tmp_path, store, legacy={case.instance: root})
    else:
        spec = {"root": root}
        if case.generic:
            spec.update({"profile": agents.GENERIC, "rules": case.generic})
        raw = device_raw(tmp_path, store, agents={case.instance: spec})
    validate(raw)
    local = tmp_path / "device.json"
    local.write_bytes(json_bytes(raw))
    return home, root, DeviceConfig(raw, local), decoys


def _record(device: DeviceConfig, instance: str) -> dict:
    return next(item for item in config_sync.local_drift(device)["targets"] if item["tool"] == instance and item["target_kind"] in agents.RULES_KINDS)


@pytest.mark.parametrize("case", CASES, ids=[case.instance for case in CASES])
def test_adapter_contract(tmp_path, monkeypatch, case):
    home, root, device, decoys = _build(tmp_path, case)
    before = _snapshot(home)

    # detect: registry agents are found where they really live
    if case.generic is None:
        host = agents.HostEnv.for_home(home, system="windows", environ={}, which=lambda name: None)
        assert case.instance in {item.instance for item in agents.detect_instances(host) if item.exists}

    # render: the entry is the documented one and the block carries a version
    (instance,) = agents.agent_instances(device.raw)
    target = agents.rules_target(instance)
    assert (target.path, target.kind) == (root / case.entry, case.kind)
    version = extract_version(sync_script._rules_body(device.raw, instance))
    assert version

    # apply + verify, without reading any protected file
    tracker = ReadTracker(monkeypatch)
    report = config_sync.sync(device, apply=True)
    monkeypatch.undo()
    assert report["verified"] is True
    assert tracker.touched(decoys) == []
    record = _record(device, case.instance)
    assert record["status"] == "applied" and record["rules_version"] == version
    applied = target.path.read_bytes()

    # repeat: nothing to write
    assert config_sync.sync(device, apply=True)["changes"] == 0

    # a hand edit inside the block is refused until the user decides
    target.path.write_bytes(applied.replace(b"<!-- ai-config:end -->", b"hand edit\n<!-- ai-config:end -->"))
    assert _record(device, case.instance)["status"] == "local_modified"
    with pytest.raises(config_sync.ConfigSyncError) as info:
        config_sync.sync(device, apply=True)
    assert info.value.exit_code == 4
    target.path.write_bytes(applied)

    # undo returns every file to its previous bytes
    latest = next(item for item in recent_operations(device.state_dir) if item["operation"] == "config")
    restore(device.state_dir, operation_id=latest["operation_id"], apply=True)
    assert _snapshot(home, files_only=True) == _snapshot_files(before)

    # detach leaves the home exactly as it was, directories included
    assert config_sync.sync(device, apply=True)["verified"] is True
    changes, detach_report = migrate.plan_detach(device.raw, local=device.source, instance_id=case.instance, state_dir=device.state_dir, restore_original=True)
    transaction(changes, device.state_dir / "backups", state_root=device.state_dir)
    migrate.remove_empty_dirs(detach_report.get("remove_dirs"))
    assert _snapshot(home) == before
    for decoy in decoys:
        assert decoy.read_bytes() == f"{SENTINEL}\n".encode("ascii")


def _snapshot_files(snapshot: dict[str, bytes | None]) -> dict[str, bytes | None]:
    return {key: value for key, value in snapshot.items() if value is not None}


def test_contract_covers_every_writable_profile():
    covered = {agents.profile_for_instance(case.instance).id if case.generic is None else agents.GENERIC for case in CASES}
    writable = {profile.id for profile in agents.PROFILES.values() if profile.writable}
    assert writable <= covered
