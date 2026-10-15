from pathlib import Path
import re

import pytest

from sync_core.machine.catalog import CATALOG, DENY, LEGACY_CATALOG, allowed_item, classify, classify_field, denied_path


def test_registry_ids_match_document_in_both_directions():
    document = (Path(__file__).resolve().parents[1] / "docs/machine-sync-classification.md").read_text(encoding="utf-8")
    section = document.split("## 4. 清单", 1)[1].split("## 5.", 1)[0]
    expected = set(re.findall(r"^\| ([A-Z]{2}-\d{2}) \|", section, re.M))
    ids = [rule.rule_id for rule in (*CATALOG, *DENY)]
    assert len(ids) == len(set(ids))
    assert set(ids) == expected
    assert all(item.rule_id and item.root and item.action for item in CATALOG)


@pytest.mark.parametrize(("root", "path", "rule", "nature"), [
    ("codex_home", "rules/default.rules", "CX-02", "A"),
    ("claude_home", "plans/one.md", "CC-04", "A"),
    ("claude_home", "projects/encoded/memory/sub/note.md", "CC-03", "A"),
    ("workbuddy_ai", "scripts/mine.py", "WB-03", "A"),
    ("codex_home", "auth.json", "CX-13", "D"),
    ("claude_desktop", "Network/Cookies", "CD-05", "D"),
    ("codex_home", "state_5.sqlite-wal", "CX-15", "E"),
    ("project:p1", ".claude/worktrees/x/.claude/settings.local.json", "PJ-06", "E"),
    ("codex_home", "skills/a/nested/app_migration.json", "SK-05", "E"),
    ("agents_home", "skills/a/SKILL.md", "SK-01", "A"),
    ("codex_home", "skills/.system/a/SKILL.md", "SK-03", "C"),
    ("codex_home", "new/unknown.dat", None, "U"),
])
def test_classification(root, path, rule, nature):
    result = classify(root, path)
    assert (result.rule_id, result.nature) == (rule, nature)


def test_origin_changes_skill_policy_and_artifacts():
    path = "skills/example/tool.exe"
    assert classify("codex_home", path, origin="user").rule_id == "SK-01"
    assert classify("codex_home", path, origin="third_party").rule_id == "SK-05"
    assert classify("codex_home", "skills/example/SKILL.md", origin="third_party").rule_id == "SK-02"
    assert classify("claude_home", "skills/example/node_modules/a.js").rule_id == "SK-05"
    assert classify("claude_home", "skills/example/.git/config").rule_id == "SK-05"


def test_field_denies_win_and_unknown_is_explicit():
    assert classify_field("claude_home", "settings.json", "env.API_TOKEN").nature == "D"
    assert classify_field("claude_home", "settings.json", "env.API_BASE_URL").rule_id == "CC-08"
    assert classify_field("claude_home", "settings.json", "language").rule_id == "CC-06"
    assert classify_field("codex_home", "config.toml", "new_setting").nature == "U"
    assert classify_field("codex_home", "config.toml", "shell_environment_policy.set.TEST_SECRET").nature == "D"


def test_ties_rejected_and_more_specific_rules_win(monkeypatch):
    from dataclasses import replace
    import sync_core.machine.catalog as catalog
    base = next(rule for rule in CATALOG if rule.rule_id == "CX-02")
    specific = replace(base, rule_id="TEST-01", pattern="rules/default.rules")
    monkeypatch.setattr(catalog, "CATALOG", (base, specific))
    assert classify("codex_home", "rules/default.rules").rule_id == "TEST-01"
    monkeypatch.setattr(catalog, "CATALOG", (specific, replace(specific, rule_id="TEST-02")))
    with pytest.raises(ValueError, match="ambiguous"):
        classify("codex_home", "rules/default.rules")


@pytest.mark.parametrize("path", ["migration.json", "skills/a/migration.json"])
def test_only_suffix_migration_marker_is_denied(path):
    assert not denied_path(path)


@pytest.mark.parametrize("path", ["_migration.json", "skills/a/b_migration.json", "skills/a/nested/b_migration.json"])
def test_all_migration_markers_denied(path):
    assert denied_path(path)


def test_legacy_selection_remains_separate_from_new_rules():
    paths = ["CLAUDE.md", "rules/sub/test.md", "settings.json", "projects/x/memory/note.md",
             "AGENTS.md", "AGENTS.override.md", "config.toml", "skills/diary/SKILL.md", "projects",
             "SOUL.md", "USER.md", "MEMORY.md", "memory/sub/note.md", ".claude/settings.local.json",
             ".workbuddy/memory/note.md", ".workbuddy-ai/skills/a/SKILL.md"]
    for item in LEGACY_CATALOG:
        for path in paths:
            old = next((rule for rule in LEGACY_CATALOG if rule.agent == item.agent and rule.instance == item.instance
                        and rule.scope == item.scope and rule.status == "approved" and rule.matches(path)
                        and (rule.kind != "memory" or path.endswith(".md"))), None)
            if not denied_path(path):
                assert allowed_item(item.agent, item.instance, path, scope=item.scope) == old
    assert allowed_item("codex", "main", "rules/default.rules") is None
    assert allowed_item("workbuddy", "workbuddy", "scripts/mine.py") is None


def test_no_parallel_file_rules_for_representative_paths():
    from sync_core.machine.catalog import _root_matches, _specificity, match_path
    for root in ("claude_home", "codex_home", "agents_home", "workbuddy", "claude_desktop", "project:p1"):
        scope = "project" if root.startswith("project:") else "agent"
        for rule in CATALOG:
            for pattern in (rule.pattern, *rule.patterns):
                if not pattern or rule.policy_only or rule.mode == "field":
                    continue
                sample = pattern.replace("**", "nested/file").replace("*", "example")
                candidates = [(max(_specificity(p) for p in (r.pattern, *r.patterns) if match_path(p, sample)), r.rule_id)
                              for r in CATALOG if _root_matches(r.root, root, scope) and r.matches(sample)]
                if candidates:
                    best = max(score for score, _ in candidates)
                    assert len([id for score, id in candidates if score == best]) == 1
