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
    rule_id: str = ""
    nature: str = ""
    action: str = ""
    group: str = ""
    root: str = ""
    text_only: bool = True
    opt_in: bool = False
    patterns: tuple[str, ...] = ()
    field_keys: tuple[str, ...] = ()
    policy_only: bool = False

    def matches(self, relative_path: str) -> bool:
        if self.policy_only or self.mode == "field":
            return False
        return any(match_path(pattern, relative_path) for pattern in (self.pattern, *self.patterns))


def match_path(pattern_text: str, relative_path: str) -> bool:
    """Segment glob: ** crosses directories; * never crosses a slash."""
    path = relative_path.replace("\\", "/")
    if path.startswith("/") or ".." in PurePosixPath(path).parts or re.match(r"^[A-Za-z]:", path):
        return False
    actual, pattern = path.split("/"), pattern_text.split("/")

    @lru_cache(None)
    def match(i: int, j: int) -> bool:
        if j == len(pattern):
            return i == len(actual)
        if pattern[j] == "**":
            return match(i, j + 1) or (i < len(actual) and match(i + 1, j))
        return i < len(actual) and fnmatchcase(actual[i], pattern[j]) and match(i + 1, j + 1)

    return match(0, 0)


LEGACY_CATALOG: tuple[CatalogItem, ...] = (
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
    *(CatalogItem(agent, agent, "persona", 1, "file", name, "manual")
      for agent in ("workbuddy", "workbuddy-ai")
      for name in ("BOOTSTRAP.md", "IDENTITY.md", "SOUL.md", "USER.md")),
    *(CatalogItem(agent, agent, "memory", 1, "file", "MEMORY.md", "manual")
      for agent in ("workbuddy", "workbuddy-ai")),
    *(CatalogItem(agent, agent, kind, 1, "file", pattern, "manual", "approved", scope)
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
    "node_modules", ".git", ".gitconfig", ".git-credentials", ".gitignore", ".gitattributes", ".gitmodules", "worktrees",
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
    if parts[-1].endswith("_migration.json"):
        return True
    return False


def allowed_item(agent: str, instance: str, relative_path: str, *, scope: str = "agent") -> CatalogItem | None:
    if denied_path(relative_path):
        return None
    root = {"claude": "claude_home", "codex": "codex_home", "workbuddy-ai": "workbuddy_ai"}.get(agent, agent)
    decision = classify(root, relative_path, scope=scope)
    if decision.nature in {"D", "E", "F"}:
        return None
    return next((item for item in LEGACY_CATALOG if item.status == "approved" and item.agent == agent
                 and item.instance == instance and item.scope == scope and item.matches(relative_path)
                 and (item.kind != "memory" or relative_path.casefold().endswith(".md"))), None)


@dataclass(frozen=True)
class DenyRule:
    rule_id: str
    root: str
    pattern: str
    nature: str
    reason: str
    patterns: tuple[str, ...] = ()
    field_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    rule_id: str | None
    nature: str
    action: str
    reason: str = ""


def _root_matches(rule_root: str, root: str, scope: str) -> bool:
    if root == "workbuddy_ai":
        root = "workbuddy"
    if rule_root == "*":
        return True
    if rule_root == "project":
        return scope == "project" or root.startswith("project:")
    return scope != "project" and rule_root == root


def _specificity(pattern: str) -> tuple[int, int, int]:
    parts = pattern.split("/")
    return (sum(not any(c in part for c in "*?[") for part in parts),
            -parts.count("**"), sum(c not in "*?[]" for c in pattern))


def classify(root: str, relative: str, *, scope: str = "agent", origin: str | None = None) -> Decision:
    """Classify names only; never open a source or infer its contents."""
    path = relative.replace("\\", "/")
    if (not path or path.startswith("/") or any(p in {"", ".", ".."} for p in path.split("/"))
            or re.match(r"^[A-Za-z]:", path) or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        return Decision(None, "D", "never", "unsafe_path")
    for rule in DENY:
        if not rule.field_keys and _root_matches(rule.root, root, scope):
            if any(match_path(p.casefold(), path.casefold()) for p in (rule.pattern, *rule.patterns)):
                return Decision(rule.rule_id, rule.nature, "never", rule.reason)
    if root == 'claude_desktop' and len(path.split('/')) == 5 and path.startswith('local-agent-mode-sessions/skills-plugin/') and path.endswith('/manifest.json'):
        return Decision('CD-01', 'C', 'record', 'source_metadata')
    matches = [(max(_specificity(p) for p in (item.pattern, *item.patterns) if match_path(p, path)), item)
               for item in CATALOG if _root_matches(item.root, root, scope) and item.matches(path)]
    if not matches:
        fields = [item for item in CATALOG if item.mode == "field"
                  and _root_matches(item.root, root, scope) and match_path(item.pattern, path)]
        if fields:
            item = min(fields, key=lambda item: item.rule_id)
            return Decision(item.rule_id, item.nature, "fields")
        return Decision(None, "U", "unclassified")
    best = max(score for score, _ in matches)
    winners = [item for score, item in matches if score == best]
    if len(winners) != 1:
        raise ValueError("ambiguous classification rules")
    item = winners[0]
    if item.rule_id == "CD-01":
        if origin != "user":
            return (Decision("CD-02", "C", "record") if origin == "vendor_builtin"
                    else Decision(None, "U", "unclassified", "manifest_required"))
        parts = path.split('/')
        if any(p in {'.git', 'node_modules', '__pycache__', '.venv'} for p in parts[5:]) or path.casefold().endswith('.pyc'):
            return Decision('SK-05', 'E', 'never', 'runtime')
    if item.kind == "skill_container":
        parts = path.split("/")
        if "skills" not in parts or len(parts) <= parts.index("skills") + 1:
            return Decision(item.rule_id, item.nature, item.action)
        skill_parts = parts[parts.index("skills") + 1:]
        builtin = skill_parts[0] == ".system" and root == "codex_home"
        if origin == "vendor_builtin" or builtin:
            return Decision("SK-03", "C", "record")
        common = {".git", "node_modules", "__pycache__", ".venv"}
        if (any(p in common for p in skill_parts) or path.casefold().endswith(".pyc")
                or origin == "third_party" and path.casefold().endswith((".exe", ".dll", ".so", ".dylib", ".node", ".pyd"))):
            return Decision("SK-05", "E", "never", "runtime")
        return Decision("SK-02", "C", "carry") if origin == "third_party" else Decision("SK-01", "A", "carry")
    return Decision(item.rule_id, item.nature, item.action)


def classify_field(root: str, source: str, key: str) -> Decision:
    """Classify a dotted field name without inspecting or returning its value."""
    if root == "codex_home" and source == "config.toml" and key.startswith("shell_environment_policy.set."):
        if re.search(r"TOKEN|KEY|SECRET|PASSWORD|AUTH", key.rsplit(".", 1)[-1], re.I):
            return Decision("CX-13", "D", "never", "credential")
    for rule in DENY:
        if _root_matches(rule.root, root, "agent") and match_path(rule.pattern, source):
            if any(fnmatchcase(key.casefold(), p.casefold()) for p in rule.field_keys):
                return Decision(rule.rule_id, rule.nature, "never", rule.reason)
    candidates = [item for item in CATALOG if item.mode == "field"
                  and _root_matches(item.root, root, "project" if root.startswith("project:") else "agent")
                  and match_path(item.pattern, source)
                  and any(fnmatchcase(key, p) for p in item.field_keys)]
    if len(candidates) > 1:
        raise ValueError("ambiguous field classification rules")
    if not candidates:
        return Decision(None, "U", "unclassified")
    item = candidates[0]
    return Decision(item.rule_id, item.nature, item.action, "confirm" if item.restore in {"confirm", "manual"} else "")


# The registry describes the target contract. Legacy collectors remain gated by
# LEGACY_CATALOG until their individual SC tasks have passed round-trip checks.
from .classification_rules import build_rules  # noqa: E402

CATALOG, DENY = build_rules(CatalogItem, DenyRule)
