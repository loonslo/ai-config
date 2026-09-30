"""Taking agents over: shared topic choices, declarations, setup and status."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sync_core import agents, config_source, config_sync, environment, wizard
from sync_core.config import DeviceConfig, load as load_config
from sync_core.restore import recent_operations
from sync_core.utils import json_bytes

from _agent_homes import build_home, device_raw, write_store

ROOT = Path(__file__).resolve().parents[1]


def _cli(local: Path, *args: str, home: Path | None = None) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if key not in {"CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME"}}
    env["PYTHONIOENCODING"] = "utf-8"
    if home is not None:
        env.update({
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(home / "AppData" / "Roaming"),
            "LOCALAPPDATA": str(home / "AppData" / "Local"),
        })
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync.py"), *args, "--local", str(local)],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(local.parent),
    )


# --------------------------------------------------------------------------
# agents.toml: topic choices shared through the store
# --------------------------------------------------------------------------

def _raw_with(tmp_path: Path, agents_toml: str | None, **declared) -> dict:
    store = write_store(tmp_path / "store")
    if agents_toml is not None:
        (store / "agents.toml").write_text(agents_toml, encoding="utf-8")
    return device_raw(tmp_path, store, agents=declared)


def test_the_store_shares_topic_choices_and_the_device_can_override(tmp_path):
    raw = _raw_with(
        tmp_path,
        '[workbuddy]\ntopics = ["security"]\n\n["workbuddy-ai"]\ntopics = ["instructions", "security"]\n',
        workbuddy={"root": tmp_path / "wb"},
        **{"workbuddy-ai": {"root": tmp_path / "wb-ai"}},
        codebuddy={"root": tmp_path / "cb", "topics": ["python"]},
    )
    topics = {instance.id: instance.topics for instance in agents.agent_instances(raw)}
    assert topics["workbuddy"] == ("security",)
    assert topics["workbuddy-ai"] == ("instructions", "security")  # the instance entry wins
    assert topics["codebuddy"] == ("python",)  # the device choice wins over everything


@pytest.mark.parametrize(
    "content, message",
    [
        ('[nobody]\ntopics = ["security"]\n', "unknown agent"),
        ('[workbuddy]\ntopics = ["gossip"]\n', "unknown topics"),
        ('[workbuddy]\ntopics = []\n', "non-empty"),
        ('[workbuddy]\nextra = 1\n', "only supports topics"),
        ("[workbuddy\n", "cannot be parsed"),
    ],
)
def test_a_broken_agents_toml_stops_instead_of_guessing(tmp_path, content, message):
    raw = _raw_with(tmp_path, content, workbuddy={"root": tmp_path / "wb"})
    with pytest.raises(ValueError, match=message):
        agents.agent_instances(raw)


def test_agents_toml_is_publishable_but_nothing_next_to_it():
    assert config_source._publishable("agents.toml")
    assert config_source._publishable("common/imported.md")
    assert not config_source._publishable("agents.toml.bak")
    assert not config_source._publishable("device.json")


# --------------------------------------------------------------------------
# declare: any Markdown-reading agent, without editing JSON
# --------------------------------------------------------------------------

def test_declare_previews_then_registers_and_can_be_undone(tmp_path):
    store = write_store(tmp_path / "store")
    local = tmp_path / "device.json"
    local.write_bytes(json_bytes(device_raw(tmp_path, store)))
    root = tmp_path / "home" / ".kiro"
    (root / "steering").mkdir(parents=True)
    before = local.read_bytes()

    preview = _cli(local, "declare", "--agent", "kiro", "--root", str(root), "--entry", "steering/ai-config.md")
    assert preview.returncode == 0, preview.stderr
    assert local.read_bytes() == before

    applied = _cli(local, "declare", "--agent", "kiro", "--root", str(root), "--entry", "steering/ai-config.md", "--apply")
    assert applied.returncode == 0, applied.stderr
    spec = load_config(local).raw["agents"]["kiro"]
    assert spec["profile"] == agents.GENERIC and spec["rules"] == {"mode": "owned_file", "path": "steering/ai-config.md"}
    assert recent_operations(tmp_path / "state")[0]["operation"] == "declare"

    again = _cli(local, "declare", "--agent", "kiro", "--root", str(root), "--entry", "steering/ai-config.md", "--apply")
    assert again.returncode == 4

    undo = _cli(local, "undo", "--index", "1", "--apply")
    assert undo.returncode == 0, undo.stderr
    assert local.read_bytes() == before


@pytest.mark.parametrize("entry", ["../outside.md", "notes.txt", "secrets/x.md"])
def test_declare_rejects_an_unsafe_entry(tmp_path, entry):
    store = write_store(tmp_path / "store")
    local = tmp_path / "device.json"
    local.write_bytes(json_bytes(device_raw(tmp_path, store)))
    result = _cli(local, "declare", "--agent", "mine", "--root", str(tmp_path / "mine"), "--entry", entry, "--apply")
    assert result.returncode == 2
    assert "agents" not in load_config(local).raw


def test_declare_can_place_a_known_agent_in_a_custom_directory(tmp_path):
    store = write_store(tmp_path / "store")
    local = tmp_path / "device.json"
    local.write_bytes(json_bytes(device_raw(tmp_path, store)))
    root = tmp_path / "portable" / "workbuddy"
    root.mkdir(parents=True)
    result = _cli(local, "declare", "--agent", "wb-portable", "--profile", "workbuddy", "--root", str(root), "--apply")
    assert result.returncode == 0, result.stderr
    (instance,) = agents.agent_instances(load_config(local).raw)
    assert instance.profile.id == "workbuddy" and agents.rules_target(instance).path == root.resolve() / "AGENTS.md"


# --------------------------------------------------------------------------
# setup and status
# --------------------------------------------------------------------------

def test_detection_lists_agents_whose_directory_exists(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("codex", "codebuddy", "workbuddy", "doubao"))
    report = environment.detect(configured={}, home=home)
    tools = {tool["tool"]: tool for tool in report["tools"]}
    assert tools["codebuddy"]["installed"] and tools["workbuddy"]["installed"]
    assert "trae" not in tools  # not installed, so not offered
    assert "doubao" not in tools  # detect-only agents are for scan, not takeover


def test_setup_registers_codex_claude_and_registry_agents(tmp_path):
    config = wizard.plan_device(
        device_id="windows-a",
        state_dir=tmp_path / "state",
        memory_repo=tmp_path / "memory",
        tools=["codex", "workbuddy", "workbuddy-ai"],
        scope=wizard.SCOPE_RULES_ONLY,
        remote_url=None,
        tool_roots={"codex": str(tmp_path / "codex"), "workbuddy": str(tmp_path / "wb"), "workbuddy-ai": str(tmp_path / "wb-ai")},
    )
    assert config["codex"] == str(tmp_path / "codex")
    assert config["agents"] == {"workbuddy": {"root": str(tmp_path / "wb")}, "workbuddy-ai": {"root": str(tmp_path / "wb-ai")}}
    with pytest.raises(wizard.SetupError, match="不支持"):
        wizard.plan_device(
            state_dir=tmp_path / "state", memory_repo=tmp_path / "memory", tools=["doubao"],
            scope=wizard.SCOPE_RULES_ONLY, remote_url=None, tool_roots={"doubao": str(tmp_path)},
        )


def test_status_names_unresolved_agents_and_sync_reports_them(tmp_path):
    store = write_store(tmp_path / "store")
    trae = tmp_path / "home" / ".trae-cn"
    trae.mkdir(parents=True)
    local = tmp_path / "device.json"
    local.write_bytes(json_bytes(device_raw(tmp_path, store, agents={"trae-cn": {"root": trae}})))
    report = config_sync.sync(DeviceConfig(load_config(local).raw, local), apply=True)
    assert report["unresolved"] and report["unresolved"][0]["instance"] == "trae-cn"
    shown = _cli(local, "status")
    assert "E1003" in shown.stdout and "TRAE" in shown.stdout
    synced = _cli(local, "sync")
    assert "E1003" in synced.stdout
