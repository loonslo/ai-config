"""Stable rule registry; paths are metadata, never executable instructions."""
from __future__ import annotations

from typing import Any


def build_rules(item_type: Any, deny_type: Any) -> tuple[tuple, tuple]:
    items, denied = [], []

    def add(id: str, root: str, paths: str, nature: str = "A", action: str = "carry",
            group: str = "rules", restore: str = "auto", *, kind: str = "rules",
            keys: str = "", policy: bool = False) -> None:
        patterns = tuple(paths.split("|"))
        agent = {"claude_home": "claude", "claude_json": "claude", "claude_desktop": "claude",
                 "codex_home": "codex", "agents_home": "shared", "workbuddy_ai": "workbuddy-ai",
                 "user_env": "system"}.get(root, root)
        items.append(item_type(agent, "desktop" if root == "claude_desktop" else "main", kind,
                               2 if restore == "manual" and nature == "B" else 3 if nature in {"D", "E", "F"} else 1,
                               "field" if keys else "file", patterns[0], restore,
                               scope="project" if root == "project" else "agent",
                               rule_id=id, nature=nature, action=action, group=group, root=root,
                               text_only=kind != "skill_container", opt_in=nature == "H",
                               patterns=patterns[1:], field_keys=tuple(keys.split("|")) if keys else (),
                               policy_only=policy))

    def deny(id: str, root: str, paths: str, nature: str = "D", keys: str = "") -> None:
        patterns = tuple(paths.split("|"))
        denied.append(deny_type(id, root, patterns[0], nature, "credential" if nature == "D" else "runtime",
                                patterns=patterns[1:], field_keys=tuple(keys.split("|")) if keys else ()))

    add("CC-01", "claude_home", "CLAUDE.md|rules/**/*.md")
    add("CC-02", "claude_home", "commands/**|agents/**|output-styles/**|keybindings.json", group="skills_own", kind="customizations")
    add("CC-03", "claude_home", "projects/*/memory/**/*.md", group="memory", kind="memory")
    add("CC-04", "claude_home", "plans/*.md", group="memory", kind="plans")
    add("CC-05", "claude_home", "skills/**", group="skills_own", kind="skill_container")
    add("CC-06", "claude_home", "settings.json", "B", "fields", "settings", keys="language|effortLevel")
    add("CC-07", "claude_home", "settings.json", "B", "fields", "settings", "confirm", keys="model|skipDangerousModePermissionPrompt")
    add("CC-08", "claude_home", "settings.json", "B", "fields", "settings", "confirm", keys="env.*")
    deny("CC-09", "claude_home", "settings.json", keys="env.*TOKEN*|env.*KEY*|env.*SECRET*|env.*PASSWORD*|env.*AUTH*")
    add("CC-10", "claude_home", "settings.json", "C", "record", "settings", "none", keys="enabledPlugins|extraKnownMarketplaces")
    add("CC-11", "claude_home", "settings.json", "B", "fields", "settings", "confirm", keys="permissions|permissions.*|hooks|hooks.*|statusLine|statusLine.*|mcpServers|mcpServers.*|outputStyle")
    deny("CC-12", "claude_home", "settings.json", keys="apiKeyHelper|awsAuthRefresh|awsCredentialExport")
    add("CC-13", "claude_json", ".claude.json", "B", "fields", "settings", "manual", keys="projects.*.hasTrustDialogAccepted|projects.*.hasClaudeMdExternalIncludesApproved")
    add("CC-14", "claude_json", ".claude.json", "B", "fields", "settings", "confirm", keys="mcpServers|mcpServers.*|projects.*.mcpServers|projects.*.mcpServers.*|enabledMcpjsonServers|disabledMcpjsonServers|allowedTools")
    # Mixed D/E remainder stays conservative; no values are needed to classify.
    deny("CC-15", "claude_json", ".claude.json", keys="oauthAccount*|userID|deviceID|installationID|account*|cached*|num*|skillUsage*|pluginUsage*|history*")
    add("CC-16", "claude_home", "plugins/**", "C", "record", "settings", "none", kind="plugins")
    deny("CC-17", "claude_home", ".credentials.json|config.json")
    add("CC-18", "claude_home", "projects/*/*.jsonl|history.jsonl", "H", "opt_in", "history", kind="history_files")
    deny("CC-19", "claude_home", "cache/**|backups/**|daemon*|daemon*/**|downloads/**|file-history/**|ide/**|jobs/**|paste-cache/**|session-env/**|sessions/**|shell-snapshots/**|teams/**|stats-cache.json|policy-limits.json|remote-settings.json|mcp-needs-auth-cache.json|skills_backup_*/**|.last-*", "E")

    add("CD-01", "claude_desktop", "local-agent-mode-sessions/skills-plugin/*/*/skills/**", group="skills_own", restore="export", kind="account_skills")
    add("CD-02", "claude_desktop", "local-agent-mode-sessions/skills-plugin/*/*/rpm/plugin_*/**", "C", "record", "skills_third", "none", kind="plugins")
    add("CD-03", "claude_desktop", "claude_desktop_config.json", "B", "fields", "settings", "confirm", keys="mcpServers|mcpServers.*|preferences|preferences.*")
    deny("CD-04", "claude_desktop", "claude-code-sessions/*.json", "E")
    deny("CD-05", "claude_desktop", "config.json|Local Storage/**|IndexedDB/**|Network/**|Partitions/**|Session Storage/**|SharedStorage/**|WebStorage/**|ant-did|ant-device-registry.json|buddy-tokens.json|ccd-ids.json|lockfile")
    deny("CD-06", "claude_desktop", "Cache/**|Code Cache/**|GPUCache/**|Dawn*/**|DIPS*|Crashpad/**|sentry/**|logs/**|claude-code/**|git-worktrees.json|mcp-user-tool-toggles.json|window-state.json|plan-usage-history.json|scratch-workspaces/**", "E")

    add("CX-01", "codex_home", "AGENTS.md|AGENTS.override.md")
    add("CX-02", "codex_home", "rules/**", group="approvals", kind="approvals")
    add("CX-03", "codex_home", "prompts/**|memories/**", group="memory", kind="memory")
    add("CX-04", "codex_home", "skills/**", group="skills_own", kind="skill_container")
    add("CX-05", "codex_home", "config.toml", "B", "fields", "settings", keys="model_reasoning_effort|personality|features|features.*|memories|memories.*|history.persistence|windows.sandbox")
    add("CX-06", "codex_home", "config.toml", "B", "fields", "settings", "confirm", keys="model|service_tier|approval_policy|sandbox_mode")
    add("CX-07", "codex_home", "config.toml", "B", "fields", "settings", "confirm", keys="shell_environment_policy.set.*")
    add("CX-08", "codex_home", "config.toml", "B", "fields", "settings", "confirm", keys="projects.*.trust_level")
    add("CX-09", "codex_home", "config.toml", "B", "fields", "settings", "confirm", keys="mcp_servers.*.url")
    add("CX-10", "codex_home", "config.toml", "C", "record", "settings", "none", keys="mcp_servers.*.command|mcp_servers.*.args|mcp_servers.*.env|mcp_servers.*.env.*")
    add("CX-11", "codex_home", "config.toml", "C", "record", "settings", "none", keys="plugins|plugins.*|marketplaces|marketplaces.*|hooks.state|notify")
    add("CX-12", "codex_home", "config.toml", "B", "fields", "settings", keys="desktop|desktop.*")
    deny("CX-13", "codex_home", "auth.json|cap_sid|installation_id|secrets/**|.sandbox-secrets/**|mcp-oauth-locks/**|chrome-native-hosts*.json")
    add("CX-14", "codex_home", "sessions/**|archived_sessions/**|session_index.jsonl|history.jsonl", "H", "opt_in", "history", kind="history_files")
    deny("CX-15", "codex_home", "*.sqlite*|.codex-global-state.json*", "E")
    deny("CX-16", "codex_home", "cache/**|plugins/**|vendor_imports/**|.tmp/**|tmp/**|log/**|sandbox*.log|.sandbox*/**|models_cache.json|cc-switch-model-catalog.json|ambient-suggestions/**|browser/**|computer-use/**|pets/**|sites/**|worktrees/**|version.json|config.toml.bak-*", "E")
    add("CX-17", "codex_home", "generated_images/**|attachments/**|visualizations/**|dictation-history/**", "F", "never", "", "none", kind="boundary")
    add("AG-01", "agents_home", "skills/**", group="skills_own", kind="skill_container")
    add("AG-02", "agents_home", ".skill-lock.json", "C", "carry", "skills_third", kind="skills")
    add("CW-01", "cc_switch", "skills/**", group="skills_own", kind="skill_container")
    deny("CW-02", "cc_switch", "cc-switch.db|settings.json|backups/**|skill-backups/**|logs/**|crash.log|model-pricing.json")

    # A single rule describes both WorkBuddy instances, selected by root alias.
    add("WB-01", "workbuddy", "BOOTSTRAP.md|IDENTITY.md|SOUL.md|USER.md|MEMORY.md|memory/**/*.md", group="memory", restore="manual", kind="persona")
    add("WB-02", "workbuddy", "skills/**", group="skills_own", restore="manual", kind="skill_container")
    add("WB-03", "workbuddy", "scripts/**", group="skills_own", restore="manual", kind="scripts")
    add("WB-04", "workbuddy", "settings.json", "C", "record", "settings", "none", keys="enabledPlugins|enabledPlugins.*")
    deny("WB-05", "workbuddy", "keyblob|security/**|app/**|user-state.json|device-id|local_storage/**|connectors*|connectors*/**|mcp-approvals.json|models.json|workspace-state.json|workspace-display-names.json|*.db*|user-*-personal/**|.workbuddy-key-fallback/**")
    deny("WB-06", "workbuddy", "sessions/**|traces/**|blobs/**|changes-*/**|artifact-index/**|audit-log/**|file-history/**|shell-snapshots/**|clipboard-images/**|logs/**|tasks/**|plans/**|cache/**|plugins/**|pending-telemetry/**", "E")
    add("WB-07", "project", ".workbuddy/memory/**|.workbuddy/skills/**|.workbuddy-ai/memory/**|.workbuddy-ai/skills/**", group="skills_own", restore="manual", kind="skill_container")
    add("WB-08", "workbuddy_tasks", "**", "F", "never", "", "none", kind="boundary")
    add("PJ-01", "project", "AGENTS.md|AGENTS.override.md|CLAUDE.md|CLAUDE.local.md")
    add("PJ-02", "project", ".claude/settings.local.json|*/.claude/settings.local.json|*/*/.claude/settings.local.json", group="approvals", kind="permissions_local")
    add("PJ-03", "project", ".claude/skills/**|.claude/commands/**|.claude/agents/**|.claude/output-styles/**|.claude/launch.json|.claude/*.md", group="skills_own", kind="skill_container")
    add("PJ-04", "project", ".agents/skills/**|.codex/config.toml|.codex/rules/**|.codex/prompts/**|.codex/skills/**", group="skills_own", kind="skill_container")
    add("PJ-05", "project", ".mcp.json", "B", "fields", "settings", "confirm", kind="settings_fields")
    deny("PJ-06", "project", ".claude/worktrees/**|.claude/shots/**|**/scratch-workspaces/**", "E")
    add("PJ-07", "project", "", "F", "never", "", "none", kind="boundary", policy=True)
    add("SY-01", "user_env", "", "B", "fields", "settings", "export", kind="env_fields", policy=True)
    deny("SY-02", "user_env", "*", keys="*KEY*|*SECRET*|*PASSWORD*|*TOKEN*")
    add("SY-03", "user_env", "", "E", "never", "", "none", policy=True)
    deny("SY-04", "*", ".ssh/**|.npmrc|credential-manager|git-credentials|**/.git-credentials")
    add("SY-05", "system", "", "C", "record", "settings", "none", kind="software", policy=True)
    add("SK-01", "*", "", group="skills_own", kind="skills", policy=True)
    add("SK-02", "*", "", "C", "carry", "skills_third", kind="skills", policy=True)
    add("SK-03", "*", "", "C", "record", "skills_third", "none", kind="skills", policy=True)
    add("SK-04", "*", "", "U", "record", "skills_own", "none", kind="copy_policy", policy=True)
    deny("SK-05", "*", "**/*_migration.json|**/.git|**/.git/**|**/.gitconfig|**/.gitignore|**/.gitattributes|**/.gitmodules", "E")
    add("OT-01", "out_of_scope", "", "F", "never", "", "none", kind="boundary", policy=True)
    return tuple(items), tuple(denied)
