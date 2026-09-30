"""``verify-load``: a challenge-response that an agent really read its rules."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sync_core import config_sync, load_check, status
from sync_core.config import DeviceConfig, load as load_config
from sync_core.utils import json_bytes

from _agent_homes import device_raw, write_store

ROOT = Path(__file__).resolve().parents[1]


def test_answers_are_parsed_from_free_text():
    assert load_check.parse_answer("好的，版本号是 3F9C2A1B。") == "3f9c2a1b"
    assert load_check.parse_answer("我不知道") is None


@pytest.mark.parametrize(
    "expected, on_disk, answer, passed, reason",
    [
        ("3f9c2a1b", "3f9c2a1b", "3f9c2a1b", True, None),
        ("3f9c2a1b", "00000000", "3f9c2a1b", False, "not_applied"),
        ("3f9c2a1b", "3f9c2a1b", "没有这个信息", False, "no_answer"),
        ("3f9c2a1b", "3f9c2a1b", "deadbeef", False, "mismatch"),
        (None, None, "3f9c2a1b", False, "no_version"),
    ],
)
def test_evaluation_names_the_reason(expected, on_disk, answer, passed, reason):
    result = load_check.evaluate(expected=expected, on_disk=on_disk, answer=answer)
    assert (result["passed"], result["reason"]) == (passed, reason)


def test_a_check_goes_stale_when_the_rules_change():
    check = {"passed": True, "version": "3f9c2a1b"}
    assert load_check.state_of(check, "3f9c2a1b") == "verified"
    assert load_check.state_of(check, "0badc0de") == "stale"
    assert load_check.state_of({"passed": False}, "3f9c2a1b") == "failed"
    assert load_check.state_of(None, "3f9c2a1b") == "unverified"


def _device(tmp_path: Path) -> tuple[Path, Path, Path]:
    store = write_store(tmp_path / "store")
    root = tmp_path / "home" / ".workbuddy"
    root.mkdir(parents=True)
    local = tmp_path / "device.json"
    local.write_bytes(json_bytes(device_raw(tmp_path, store, agents={"workbuddy": {"root": root}})))
    return store, root, local


def _cli(local: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync.py"), *args, "--local", str(local)],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )


def test_verify_load_end_to_end(tmp_path):
    store, root, local = _device(tmp_path)
    device = DeviceConfig(load_config(local).raw, local)
    config_sync.sync(device, apply=True)
    version = load_check.extract_version((root / "AGENTS.md").read_bytes())

    instructions = _cli(local, "verify-load", "--agent", "workbuddy")
    assert instructions.returncode == 0 and load_check.QUESTION in instructions.stdout
    assert version not in instructions.stdout  # the challenge does not give the answer away

    wrong = _cli(local, "verify-load", "--agent", "workbuddy", "--answer", "deadbeef", "--apply")
    assert wrong.returncode == 2 and "E6001" in wrong.stderr

    right = _cli(local, "verify-load", "--agent", "workbuddy", "--answer", f"版本是 {version}", "--apply", "--json")
    assert right.returncode == 0, right.stdout + right.stderr
    assert json.loads(right.stdout)["status"] == "passed"

    record = next(item for item in config_sync.local_drift(device)["targets"] if item["tool"] == "workbuddy")
    assert record["load_check"] == "verified"
    receipt = status.shared_receipt(config_sync.state_for(device))
    (target,) = receipt["target_digests"]
    assert target["load_verified"] is True
    assert "deadbeef" not in json.dumps(receipt) and version not in json.dumps({k: v for k, v in target.items() if k != "expected_digest"})

    # Editing a shared rule makes the old proof stale until it is repeated.
    (store / "common" / "security.md").write_text("# security\n\n- a new rule\n", encoding="utf-8")
    record = next(item for item in config_sync.local_drift(device)["targets"] if item["tool"] == "workbuddy")
    assert record["load_check"] == "stale"

    shown = _cli(local, "status")
    assert "加载核验" in shown.stdout


def test_verify_load_refuses_an_unknown_or_unresolved_agent(tmp_path):
    store = write_store(tmp_path / "store")
    trae = tmp_path / "home" / ".trae-cn"
    trae.mkdir(parents=True)
    local = tmp_path / "device.json"
    local.write_bytes(json_bytes(device_raw(tmp_path, store, agents={"trae-cn": {"root": trae}})))
    assert _cli(local, "verify-load", "--agent", "nobody").returncode == 2
    unresolved = _cli(local, "verify-load", "--agent", "trae-cn")
    assert unresolved.returncode == 2 and "TRAE" in unresolved.stderr
