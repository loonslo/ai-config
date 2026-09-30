"""``scan``: read-only inventory of every agent in a sandbox home.

The sandbox replicates real agent layouts with placeholder content.  The tests
prove three things: what is reported is right, protected files are never opened,
and nothing is written.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sync_core import agents, scan as scanner

from _agent_homes import HAND_WRITTEN_RULES, SENTINEL, ReadTracker, build_home, write_store

ROOT = Path(__file__).resolve().parents[1]


def _host(home: Path) -> agents.HostEnv:
    return agents.HostEnv.for_home(home, system="windows", environ={}, which=lambda name: None)


def _store(tmp_path: Path) -> Path:
    # The store already holds the first two hand-written lines, not the rest.
    return write_store(tmp_path / "store", instructions="# Developer Profile\n\n## Coding Style\n\n- 默认使用 Python 3.14\n")


def _row(report: dict, instance: str) -> dict:
    return next(row for row in report["agents"] if row["instance"] == instance)


def _tree(root: Path) -> list[tuple[str, int]]:
    return sorted((str(path.relative_to(root)), path.stat().st_size if path.is_file() else -1) for path in root.rglob("*"))


def test_scan_reports_every_agent_without_reading_protected_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    protected = build_home(home)["protected"]
    store = _store(tmp_path)
    before = _tree(home)
    tracker = ReadTracker(monkeypatch)
    report = scanner.scan(_host(home), store_root=store)
    text = scanner.render(report)
    monkeypatch.undo()

    assert tracker.touched(protected) == []
    assert SENTINEL not in json.dumps(report, ensure_ascii=False)
    assert SENTINEL not in text
    assert _tree(home) == before

    instances = {row["instance"] for row in report["agents"]}
    assert {"codex", "claude", "codebuddy", "workbuddy", "workbuddy-ai", "cc-switch", "doubao"} <= instances
    assert _row(report, "doubao")["level"] == agents.LEVEL_DETECT
    assert _row(report, "cc-switch")["kind"] == "manager"
    assert "只读盘点" in text


def test_hand_written_rules_are_compared_with_the_store(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("codex",))
    report = scanner.scan(_host(home), store_root=_store(tmp_path))
    codex = _row(report, "codex")
    assert codex["rules"]["state"] == "unmanaged"
    analysis = codex["rules"]["analysis"]
    # "# Developer Profile", "## Coding Style" and the Python line are known;
    # the pytest line is not.
    assert (analysis["lines"], analysis["known_lines"], analysis["unique_lines"]) == (4, 3, 1)
    assert codex["migratable"] == ["AGENTS.md"]


def test_the_managed_block_is_not_counted_as_hand_written(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("codex",))
    agents_md = home / ".codex" / "AGENTS.md"
    agents_md.write_bytes(b"<!-- ai-config:begin -->\n- shared rule nobody wrote by hand\n<!-- ai-config:end -->\n")
    report = scanner.scan(_host(home), store_root=_store(tmp_path))
    rules = _row(report, "codex")["rules"]
    assert rules["state"] == "managed"
    assert rules["analysis"]["lines"] == 0
    assert _row(report, "codex")["migratable"] == []


def test_workbuddy_persona_memory_and_protected_items_are_named_only(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("workbuddy",))
    report = scanner.scan(_host(home), store_root=_store(tmp_path))
    row = _row(report, "workbuddy")
    assert row["rules"]["state"] == "missing" and row["rules"]["entry"] == "AGENTS.md"
    assert set(row["persona"]) == {"SOUL.md", "USER.md", "IDENTITY.md"}
    assert {item["path"] for item in row["memory"]} == {"MEMORY.md", "memory"}
    assert {"keyblob", "security", "app/connector-keys"} <= set(row["protected"])
    assert "settings.json" in row["settings"]


def test_codebuddy_owned_file_and_existing_rules(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("codebuddy",))
    (home / ".codebuddy" / "CODEBUDDY.md").write_bytes(HAND_WRITTEN_RULES.encode("utf-8"))
    report = scanner.scan(_host(home), store_root=_store(tmp_path))
    row = _row(report, "codebuddy")
    assert (row["rules"]["entry"], row["rules"]["mode"], row["rules"]["state"]) == ("rules/ai-config.md", agents.MODE_FILE, "missing")
    (existing,) = row["existing_rules"]
    assert existing["path"] == "CODEBUDDY.md" and existing["unique_lines"] == 1


def test_a_foreign_file_at_the_owned_entry_is_reported(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("codebuddy",))
    entry = home / ".codebuddy" / "rules" / "ai-config.md"
    entry.parent.mkdir(parents=True)
    entry.write_bytes(b"# someone else's file\n")
    row = _row(scanner.scan(_host(home), store_root=_store(tmp_path)), "codebuddy")
    assert row["rules"]["state"] == "foreign"


def test_trae_is_probed_and_its_existing_rules_listed(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("trae-cn-dir",))
    row = _row(scanner.scan(_host(home), store_root=_store(tmp_path)), "trae-cn")
    assert row["rules"]["entry"] == "user_rules/ai-config.md"
    assert [item["path"] for item in row["existing_rules"]] == ["user_rules/AGENTS.md"]


def test_an_unresolvable_trae_entry_is_explained(tmp_path):
    home = tmp_path / "home"
    (home / ".trae").mkdir(parents=True)
    row = _row(scanner.scan(_host(home), store_root=_store(tmp_path)), "trae")
    assert row["rules"]["state"] == "unresolved"
    assert "TRAE" in row["rules"]["reason"]


def test_a_codex_override_file_is_flagged(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("codex",))
    (home / ".codex" / "AGENTS.override.md").write_bytes(b"override\n")
    report = scanner.scan(_host(home), store_root=_store(tmp_path))
    assert _row(report, "codex")["shadowed_by"] == ["AGENTS.override.md"]
    assert "AGENTS.override.md" in scanner.render(report)


def test_a_rules_file_holding_a_secret_is_blocked_and_withheld(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("codex",))
    # Assembled at runtime so the repository secret scan does not flag the test.
    key_name = "API" + "_KEY"
    (home / ".codex" / "AGENTS.md").write_bytes(f"{key_name}={SENTINEL}\n".encode("ascii"))
    report = scanner.scan(_host(home), store_root=_store(tmp_path))
    assert _row(report, "codex")["rules"]["state"] == "blocked_secret"
    assert SENTINEL not in json.dumps(report) and SENTINEL not in scanner.render(report)


def test_skills_are_inventoried_across_agents(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("codex", "claude", "codebuddy", "workbuddy", "workbuddy-ai", "cc-switch", "agents-skills"))
    skills = scanner.scan(_host(home), store_root=_store(tmp_path))["skills"]
    by_name = {item["name"]: item for item in skills["skills"]}
    assert by_name["review"]["state"] == "conflict"  # cc-switch holds a different copy
    assert by_name["diary"]["state"] == "duplicate"  # codex + the shared .agents directory
    assert by_name["office"]["state"] == "duplicate"  # both WorkBuddy instances
    assert "builtin" not in by_name  # hidden system skills are not the user's
    assert skills["writes"] is False


def _link_directory(link: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_a_linked_skills_directory_is_attributed_to_its_manager(tmp_path):
    home = tmp_path / "home"
    build_home(home, agents=("claude", "cc-switch"))
    import shutil

    shutil.rmtree(home / ".claude" / "skills")
    try:
        _link_directory(home / ".claude" / "skills", home / ".cc-switch" / "skills")
    except OSError as error:  # pragma: no cover - platform without link support
        pytest.skip(f"cannot create a directory link here: {error}")
    sources = scanner.scan(_host(home), store_root=_store(tmp_path))["skills"]["sources"]
    claude = next(source for source in sources if source["owner"] == "claude")
    assert claude["link"] is True and claude["managed_by"] == "cc-switch"


def test_scan_command_runs_without_a_device_configuration_and_writes_nothing(tmp_path):
    home = tmp_path / "home"
    build_home(home)
    before = _tree(home)
    env = {key: value for key, value in os.environ.items() if key not in {"CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME"}}
    env.update({
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "PYTHONIOENCODING": "utf-8",
    })
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync.py"), "scan", "--json", "--local", str(tmp_path / "absent.json")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["read_only"] is True and report["saved"] is None
    assert {"codex", "workbuddy"} <= {row["instance"] for row in report["agents"]}
    assert SENTINEL not in result.stdout + result.stderr
    assert _tree(home) == before
    assert not (tmp_path / "absent.json").exists()
