from sync_core.machine.catalog import allowed_item, denied_path


def test_catalog_is_default_deny_and_limits_approved_workbuddy_scope():
    assert allowed_item("claude", "main", "CLAUDE.md") is not None
    assert allowed_item("claude", "main", "rules/nested/personal.md") is not None
    assert allowed_item("claude", "main", "rules/personal.md") is not None
    assert allowed_item("claude", "main", "projects/encoded/memory/note.md") is not None
    assert allowed_item("claude", "main", "projects/encoded/memory/session.jsonl") is None
    assert allowed_item("codex", "main", "skills/mine/SKILL.md") is not None
    workbuddy = allowed_item("workbuddy", "workbuddy", "SOUL.md")
    assert workbuddy is not None and workbuddy.restore == "manual"
    assert allowed_item("workbuddy", "workbuddy", "settings.json") is None
    assert allowed_item("workbuddy", "workbuddy", "scripts/private.py") is None
    assert allowed_item("claude", "main", "unknown.json") is None
    for path in ("auth.json", ".credentials.json", "security/token", "app/db", "keyblob", "local_storage/x", "skills/.system/SKILL.md", "skills/a/x.db", "skills/a/x.db-journal", "connectors-mail/x", "../escape", "C:/escape"):
        assert denied_path(path)
