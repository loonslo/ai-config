"""Explicit allowlist for machine backup content; unknown sources are denied."""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import PurePosixPath
import re


@dataclass(frozen=True)
class CatalogItem:
    agent: str
    instance: str
    kind: str
    tier: int
    mode: str
    pattern: str
    restore: str
    status: str = "approved"
    scope: str = "agent"

    def matches(self, relative_path: str) -> bool:
        path = relative_path.replace("\\", "/")
        if path.startswith("/") or ".." in PurePosixPath(path).parts or re.match(r"^[A-Za-z]:", path):
            return False
        if self.mode == "fields":
            return path == self.pattern
        actual, pattern = path.split("/"), self.pattern.split("/")

        @lru_cache(None)
        def match(i: int, j: int) -> bool:
            if j == len(pattern):
                return i == len(actual)
            if pattern[j] == "**":
                return match(i, j + 1) or (i < len(actual) and match(i + 1, j))
            return i < len(actual) and fnmatchcase(actual[i], pattern[j]) and match(i + 1, j + 1)

        return match(0, 0)


CATALOG: tuple[CatalogItem, ...] = (
    CatalogItem("claude", "main", "rules", 1, "file", "CLAUDE.md", "auto"),
    CatalogItem("claude", "main", "rules", 1, "file", "rules/**/*.md", "auto"),
    CatalogItem("claude", "main", "settings_fields", 1, "fields", "settings.json", "auto"),
    CatalogItem("claude", "main", "memory", 1, "file", "projects/**/memory/**", "auto"),
    CatalogItem("claude", "main", "permissions_local", 1, "file", ".claude/settings.local.json", "auto", scope="project"),
    CatalogItem("claude", "main", "trust_fields", 2, "fields", ".claude.json", "manual"),
    CatalogItem("codex", "main", "rules", 1, "file", "AGENTS.md", "auto"),
    CatalogItem("codex", "main", "rules", 1, "file", "AGENTS.override.md", "auto"),
    CatalogItem("codex", "main", "settings_fields", 1, "fields", "config.toml", "auto"),
    CatalogItem("codex", "main", "skills_text", 1, "file", "skills/**", "auto"),
    CatalogItem("codex", "main", "trust_fields", 1, "fields", "projects", "confirm"),
    *(CatalogItem(agent, agent, "persona", 1, "file", name, "auto", "draft")
      for agent in ("workbuddy", "workbuddy-ai")
      for name in ("BOOTSTRAP.md", "IDENTITY.md", "SOUL.md", "USER.md", "MEMORY.md")),
    *(CatalogItem(agent, agent, kind, 1, "file", pattern, "auto", "draft", scope)
      for agent in ("workbuddy", "workbuddy-ai")
      for kind, pattern, scope in (("memory", "memory/**", "agent"), ("skills_text", "skills/**", "agent"),
                                   ("memory", f".{agent}/memory/**", "project"), ("skills_text", f".{agent}/skills/**", "project"))),
    *(CatalogItem(agent, agent, "settings_fields", 1, "fields", "settings.json", "confirm", "draft")
      for agent in ("workbuddy", "workbuddy-ai")),
)

CLAUDE_FIELDS_AUTO = ("language", "effortLevel")
CLAUDE_FIELDS_CONFIRM = ("model", "skipDangerousModePermissionPrompt")
CODEX_FIELDS_AUTO = (
    "model_reasoning_effort", "personality", "features.*", "memories.*",
    "history.persistence", "windows.sandbox",
)
CODEX_FIELDS_CONFIRM = ("model", "service_tier", "approval_policy", "sandbox_mode")
CODEX_DESKTOP_FIELDS = frozenset({"codeFontSize", "sansFontSize", "localeOverride", "conversationDetailMode"})

NEVER_NAMES = frozenset({
    "auth.json", ".credentials.json", "keyblob", "user-state.json", "device-id",
    "models.json", "workspace-state.json", "workspace-display-names.json",
})
NEVER_PARTS = frozenset({
    "security", "app", "local_storage", "runtime", "logs", "cache", ".system",
    "node_modules", ".git", "worktrees",
})


def denied_path(relative_path: str) -> bool:
    """Reject protected, runtime, link-owned and unknown-risk names early."""
    path = PurePosixPath(relative_path.replace("\\", "/"))
    parts = tuple(part.casefold() for part in path.parts)
    if path.is_absolute() or not parts or ".." in parts or re.match(r"^[A-Za-z]:", relative_path):
        return True
    if any(ord(char) < 32 or ord(char) == 127 for char in relative_path):
        return True
    if any(part in NEVER_PARTS or part in NEVER_NAMES for part in parts):
        return True
    if any(part.startswith("connectors") or re.search(r"\.(?:db|sqlite|sqlite3)(?:$|[.-])", part) for part in parts):
        return True
    if parts[-1].startswith(".") and parts[-1].endswith("_migration.json"):
        return True
    return False


def allowed_item(agent: str, instance: str, relative_path: str, *, scope: str = "agent") -> CatalogItem | None:
    if denied_path(relative_path):
        return None
    return next((item for item in CATALOG if item.status == "approved" and item.agent == agent
                 and item.instance == instance and item.scope == scope and item.matches(relative_path)
                 and (item.kind != "memory" or relative_path.casefold().endswith(".md"))), None)
