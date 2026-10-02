from __future__ import annotations

import json
from pathlib import Path

from sync_core.config import SHARED_RULE_TOPICS
from sync_core.package.policy import collect_portable_config


def _store(root: Path) -> None:
    common = root / "common"
    common.mkdir(parents=True)
    for topic in SHARED_RULE_TOPICS:
        (common / f"{topic}.md").write_text(f"# {topic}\n", encoding="utf-8")


def test_collection_reads_only_allowlisted_shared_content_and_strips_device_paths(tmp_path):
    store = tmp_path / "store"
    _store(store)
    (store / "codex").mkdir()
    (store / "codex" / "config.toml").write_text('approval_policy = "on-request"\n', encoding="utf-8")
    (store / "claude").mkdir()
    (store / "claude" / "settings.shared.json").write_text('{"autoMemoryEnabled": true}\n', encoding="utf-8")
    (store / "agents.toml").write_text('[workbuddy]\ntopics = ["instructions", "security"]\n', encoding="utf-8")
    local_agent_root = tmp_path / "local-agent-root"
    config = {
        "device": "windows-machine-a",
        "state_dir": str(tmp_path / "private-state"),
        "memory_repo": str(tmp_path / "private-memory"),
        "codex": str(local_agent_root / ".codex"),
        "codex_keys": ["approval_policy"],
        "claude_keys": ["autoMemoryEnabled"],
        "codex_overrides": {"approval_policy": "local-only-value"},
        "claude_overrides": {"autoMemoryEnabled": False},
        "agents": {
            "workbuddy-custom": {
                "profile": "workbuddy",
                "root": str(local_agent_root),
                "topics": ["instructions", "security"],
            }
        },
    }

    report = collect_portable_config(config, store)
    sources = {entry.logical_source for entry in report.entries}
    contents = b"\n".join(entry.content for entry in report.entries)

    assert len(report.entries) == len(SHARED_RULE_TOPICS) + 4
    assert "settings://codex/main/approval_policy" in sources
    assert "settings://claude/main/autoMemoryEnabled" in sources
    assert "agent://shared/declarations.json" in sources
    assert "agent://shared/agents-registry.json" in sources
    assert str(local_agent_root).encode() not in contents
    assert b"windows-machine-a" not in contents
    assert b"local-only-value" not in contents
    assert b"workbuddy-custom" not in contents
    assert report.ready_without_review


def test_suspicious_rule_credentials_are_excluded_and_local_paths_require_review(tmp_path):
    store = tmp_path / "store"
    _store(store)
    secret_source = store / "common" / "instructions.md"
    sample = 'api_key = "' + "sk-" + "abcdefghijklmnopqrstuv123456" + '"\n'
    secret_source.write_text(sample, encoding="utf-8")
    project_path = tmp_path / "local-project"
    (store / "common" / "principles.md").write_text(f"Use this repo: {project_path}\n", encoding="utf-8")

    report = collect_portable_config({"projects": {"demo": str(project_path)}}, store)

    issues = {issue.logical_source: issue for issue in report.exclusions}
    assert issues["agent://shared/common/instructions.md"].category == "sensitive"
    review = next(issue for issue in report.review_required if issue.logical_source == "agent://shared/common/principles.md")
    assert review.category == "local_only"
    assert review.line_numbers == (1,)
    assert all(entry.logical_source not in {secret_source.as_posix(), "agent://shared/common/principles.md"} for entry in report.entries)
    summary = json.dumps(report.public_summary(), ensure_ascii=False)
    assert str(project_path) not in summary
    assert ("sk-" + "abcdefghijklmnopqrstuv123456") not in summary
    assert report.ready_without_review is False


def test_protected_agent_files_and_unknown_store_files_are_never_opened(tmp_path, monkeypatch):
    store = tmp_path / "store"
    _store(store)
    agent_root = tmp_path / "agent"
    decoy = agent_root / ".claude.json"
    decoy.parent.mkdir()
    decoy.write_text("DO NOT READ protected credential decoy", encoding="utf-8")
    nested_decoy = agent_root / "sessions" / "runtime.sqlite"
    nested_decoy.parent.mkdir()
    nested_decoy.write_text("DO NOT READ runtime decoy", encoding="utf-8")
    unknown = store / "unknown-state.json"
    unknown.write_text("DO NOT OPEN unknown file", encoding="utf-8")

    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        assert path not in {decoy, nested_decoy, unknown}
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    report = collect_portable_config({"codex": str(agent_root)}, store)

    assert len(report.entries) == len(SHARED_RULE_TOPICS)
    assert report.unclassified_top_level_count == 1
    assert all("unknown" not in entry.logical_source for entry in report.entries)


def test_windows_and_unc_paths_are_flagged_without_path_substitution(tmp_path):
    store = tmp_path / "store"
    _store(store)
    source = store / "common" / "engineering.md"
    source.write_text("Windows: C:\\Users\\alice\\project\nNetwork: \\\\host\\share\\repo\n", encoding="utf-8")

    report = collect_portable_config({}, store)

    issue = next(item for item in report.review_required if item.logical_source == "agent://shared/common/engineering.md")
    assert issue.line_numbers == (1, 2)
    assert source.read_text(encoding="utf-8").startswith("Windows:")
    assert report.ready_without_review is False


def test_non_file_agent_registry_is_reported_without_reading_it(tmp_path):
    store = tmp_path / "store"
    _store(store)
    (store / "agents.toml").mkdir()

    report = collect_portable_config({}, store)

    issue = next(item for item in report.exclusions if item.logical_source == "agent://shared/agents.toml")
    assert issue.category == "protected"
