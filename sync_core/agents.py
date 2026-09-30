"""Agent adapter registry.

ai-config synchronizes one configuration store into many AI agents.  This
module is the single place that knows which agents exist, where each keeps its
configuration on every platform, which one file ai-config may write for it, and
which files it must never open.

Profiles are plain data.  Nothing is loaded from a user file and nothing in a
profile is executed; a device may only *select* a profile (and, for the generic
profile, declare one relative Markdown entry).  Adding an agent means adding a
profile, a fixture home and passing the shared contract tests: the planners,
the verifier, the scanner and the status report all read from here.

Levels
------
``detect`` (L0)
    The agent is recognized and reported.  ai-config never writes to it.
``rules`` (L1)
    ai-config writes exactly the managed rules entry declared here.

Scalar settings (L2) stay limited to the verified Codex/Claude allowlists in
``sync_core.config``; skills, MCP and memory (L3) are not written.
"""
from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
from typing import Any, Callable, Iterable, Mapping

LEVEL_DETECT = "detect"
LEVEL_RULES = "rules"

#: The managed rules block lives inside a file the user also edits.
MODE_BLOCK = "managed_block"
#: The whole file belongs to ai-config; it contains nothing but the block.
MODE_FILE = "owned_file"
#: TRAE keeps global rules either as a directory of files or as one file,
#: depending on the version, so the entry is decided by looking.
MODE_PROBE_TRAE = "probe_trae"

#: Modes a device may declare for a generic agent.
DECLARABLE_MODES = (MODE_BLOCK, MODE_FILE)

#: ``target_kind`` values used by the verifier and the status report.
KIND_BLOCK = "rules_block"
KIND_FILE = "rules_file"
RULES_KINDS = (KIND_BLOCK, KIND_FILE)

#: Name of the file ai-config owns inside a rules directory.
OWNED_FILE_NAME = "ai-config.md"

GENERIC = "generic"

#: Credential and login material that no agent profile may ever have read.  The
#: per-profile lists add tool-specific names on top of these.
COMMON_SENSITIVE = (
    "auth.json", ".credentials.json", "credentials.json", "*.pem", "*.key", "*.p12",
    "keyblob", "secrets", ".env", "*.env", "id_rsa*", "cookies*",
)


@dataclass(frozen=True)
class Location:
    """One place an agent instance may keep its configuration root."""

    instance: str
    template: str
    system: str = "*"


@dataclass(frozen=True)
class RulesEntry:
    mode: str
    path: str = ""


@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    level: str
    kind: str
    locations: tuple[Location, ...] = ()
    root_env: tuple[str, ...] = ()
    executables: tuple[str, ...] = ()
    rules: RulesEntry | None = None
    #: Rule topics this agent receives by default; ``None`` means all topics.
    topics: tuple[str, ...] | None = None
    #: User-authored rule files or directories analyzed by scan/migrate.
    existing_rules: tuple[str, ...] = ()
    #: Files that, when present, make the agent ignore the managed entry.
    shadowed_by: tuple[str, ...] = ()
    #: Report-only groups: listed by name, never read, never written.
    persona: tuple[str, ...] = ()
    memory: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    settings: tuple[str, ...] = ()
    sensitive: tuple[str, ...] = ()
    runtime: tuple[str, ...] = ()
    #: For management tools: what they take over, shown so ai-config stays clear.
    manages: tuple[str, ...] = ()
    #: Where the entry knowledge comes from (official docs, community, ...).
    evidence: str = ""

    @property
    def instances(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for location in self.locations:
            seen.setdefault(location.instance, None)
        return tuple(seen)

    @property
    def writable(self) -> bool:
        return self.level == LEVEL_RULES


def _home(template: str, instance: str | None = None) -> Location:
    return Location(instance or template.rsplit("/", 1)[-1].lstrip(".").casefold(), "{home}/" + template)


_CODEX_RUNTIME = (
    "sessions", "archived_sessions", "history.jsonl", "session_index.jsonl", "log", "logs_*",
    "*.sqlite", "*.sqlite-*", "sqlite", "cache", ".tmp", "tmp", "shell_snapshots", "worktrees",
    "attachments", "generated_images", "visualizations", "browser", "computer-use", "node_repl",
    "process_manager", "thread-writer-locks", "project-metadata-locks", "mcp-oauth-locks",
    "rollout-migrations", "sandbox*", ".sandbox*", "models_cache.json", "version.json",
    ".codex-global-state*", "..codex-global-state*", "*.tmp-*",
)

_WORKBUDDY_RUNTIME = (
    "*.db", "*.db-shm", "*.db-wal", "sessions", "logs", "audit-log", "cache", "blobs", "traces",
    "file-history", "file-tree-manifests", "changes-detail", "changes-index", "artifact-index",
    "shell-snapshots", "clipboard-images", "pending-telemetry", "wbipc", "tasks", "plans",
    "projects", "workspace", "workspace-state.json", "workspace-display-names.json", "app",
    "binaries", "storage", "editor-sdk-sandbox-ws", "inspiration", "assistant-display",
    "skill-cloud-sync", "plugins", "plugin-marketplace-state*", "connectors-marketplace",
    "skills-marketplace", ".workbuddy-sqlite-migrations", ".skill-list-cache.json",
    ".skills-marketplace-version", ".connectors-marketplace.meta.json", "epoch-marker.json",
    "failover.json", "last-launch.json", "session_fragment_repair_done*", "usage-log.json",
    "tencent-docs-engine.port", "project-resources", ".legacy-localstorage-migration.done",
    "ioa-im-override.json", "mcp-tool-list.json", "agent-cli-mcp-config", "*-*-*-*-*",
)

PROFILES: dict[str, AgentProfile] = {
    "codex": AgentProfile(
        id="codex",
        name="Codex",
        level=LEVEL_RULES,
        kind="coding",
        locations=(_home(".codex"),),
        root_env=("CODEX_HOME",),
        executables=("codex",),
        rules=RulesEntry(MODE_BLOCK, "AGENTS.md"),
        existing_rules=("AGENTS.md",),
        shadowed_by=("AGENTS.override.md",),
        memory=("memories",),
        skills=("skills",),
        settings=("config.toml",),
        sensitive=("secrets", ".sandbox-secrets", "cap_sid", "installation_id"),
        runtime=_CODEX_RUNTIME,
        evidence="现有实现：全局规则读取 AGENTS.md；存在 AGENTS.override.md 时优先读取后者",
    ),
    "claude": AgentProfile(
        id="claude",
        name="Claude Code",
        level=LEVEL_RULES,
        kind="coding",
        locations=(_home(".claude"),),
        root_env=("CLAUDE_CONFIG_DIR",),
        executables=("claude",),
        rules=RulesEntry(MODE_BLOCK, "CLAUDE.md"),
        existing_rules=("CLAUDE.md", "rules"),
        memory=("projects",),
        skills=("skills",),
        settings=("settings.json", "settings.local.json"),
        sensitive=(".claude.json", "*.credentials*"),
        runtime=(
            "sessions", "history.jsonl", "shell-snapshots", "paste-cache", "file-history", "cache",
            "downloads", "ide", "statsig", "todos", "plans", "jobs", "tasks", "teams", "daemon*",
            "backups", "session-env", "stats-cache.json", "mcp-needs-auth-cache.json",
            "policy-limits.json", "remote-settings.json", "config.json", "plugins", ".last-*",
            "skills_backup_*",
        ),
        evidence="现有实现：全局规则读取 CLAUDE.md，用户规则目录 ~/.claude/rules/",
    ),
    "codebuddy": AgentProfile(
        id="codebuddy",
        name="CodeBuddy",
        level=LEVEL_RULES,
        kind="coding",
        locations=(_home(".codebuddy"),),
        executables=("codebuddy", "cbc"),
        rules=RulesEntry(MODE_FILE, f"rules/{OWNED_FILE_NAME}"),
        existing_rules=("CODEBUDDY.md", "rules"),
        memory=("memery", "memory"),
        skills=("skills",),
        settings=("settings.json", "mcp.json"),
        sensitive=("models.json", "connectors"),
        runtime=(
            "logs", "diagnostics", "inspiration", "extensions", "plugins", "skills-marketplace*",
            "expert-history.json", "argv.json", ".built-in.install.lock", ".skills-marketplace-version",
        ),
        evidence="官方文档：用户规则 ~/.codebuddy/rules/*.md，用户记忆 ~/.codebuddy/CODEBUDDY.md",
    ),
    "workbuddy": AgentProfile(
        id="workbuddy",
        name="WorkBuddy",
        level=LEVEL_RULES,
        kind="office",
        locations=(_home(".workbuddy"), _home(".workbuddy-ai")),
        rules=RulesEntry(MODE_BLOCK, "AGENTS.md"),
        topics=("instructions", "principles", "security"),
        existing_rules=("AGENTS.md",),
        persona=("SOUL.md", "USER.md", "IDENTITY.md", "BOOTSTRAP.md"),
        memory=("MEMORY.md", "memory"),
        skills=("skills",),
        settings=("settings.json", "mcp-approvals.json"),
        sensitive=(
            "security", "connector-keys", "app/connector-keys", "models.json", "device-id",
            "local_storage", "plugin-account-state", "user-state.json", "qimei-cache.json", "connectors",
        ),
        runtime=_WORKBUDDY_RUNTIME,
        evidence="社区文档：~/.workbuddy/AGENTS.md 为用户自写的工作手册；需加载核验，备选 USER.md",
    ),
    "trae": AgentProfile(
        id="trae",
        name="TRAE",
        level=LEVEL_RULES,
        kind="coding",
        locations=(_home(".trae"), _home(".trae-cn")),
        executables=("trae", "trae-cn"),
        rules=RulesEntry(MODE_PROBE_TRAE),
        existing_rules=("user_rules", "user_rules.md"),
        memory=("memory",),
        skills=("skills",),
        runtime=("logs", "cache", "extensions"),
        evidence="官方文档：全局规则 ~/.trae/user_rules（国内版 ~/.trae-cn/user_rules）；目录或文件形态需探测",
    ),
    GENERIC: AgentProfile(
        id=GENERIC,
        name="自定义 agent",
        level=LEVEL_RULES,
        kind="custom",
        evidence="由用户声明的 Markdown 规则入口；需 verify-load 确认 agent 确实读取",
    ),
    "kiro": AgentProfile(
        id="kiro",
        name="Kiro",
        level=LEVEL_DETECT,
        kind="coding",
        locations=(
            _home(".kiro", "kiro"),
            Location("kiro", "{appdata}/Kiro", "windows"),
            Location("kiro", "{home}/Library/Application Support/Kiro", "macos"),
        ),
        executables=("kiro",),
        evidence="候选：全局 steering 目录 ~/.kiro/steering/（待核对文档与沙箱实测）",
    ),
    "opencode": AgentProfile(
        id="opencode",
        name="opencode",
        level=LEVEL_DETECT,
        kind="coding",
        locations=(
            Location("opencode", "{xdg_config}/opencode"),
            Location("opencode", "{appdata}/ai.opencode.desktop", "windows"),
        ),
        executables=("opencode",),
        evidence="候选：~/.config/opencode/AGENTS.md（待核对文档与沙箱实测）",
    ),
    "gemini": AgentProfile(
        id="gemini",
        name="Gemini CLI",
        level=LEVEL_DETECT,
        kind="coding",
        locations=(_home(".gemini", "gemini"),),
        executables=("gemini",),
        evidence="候选：~/.gemini/GEMINI.md（待核对文档与沙箱实测）",
    ),
    "copilot": AgentProfile(
        id="copilot",
        name="GitHub Copilot CLI",
        level=LEVEL_DETECT,
        kind="coding",
        locations=(_home(".copilot", "copilot"),),
        executables=("copilot",),
        evidence="仅识别；规则入口待核对",
    ),
    "kimi": AgentProfile(
        id="kimi",
        name="Kimi Code",
        level=LEVEL_DETECT,
        kind="coding",
        locations=(_home(".kimi", "kimi"), Location("kimi", "{localappdata}/kimi-code", "windows")),
        executables=("kimi",),
        evidence="仅识别；规则入口待核对",
    ),
    "cursor": AgentProfile(
        id="cursor",
        name="Cursor",
        level=LEVEL_DETECT,
        kind="coding",
        locations=(
            _home(".cursor", "cursor"),
            Location("cursor", "{appdata}/Cursor", "windows"),
            Location("cursor", "{home}/Library/Application Support/Cursor", "macos"),
        ),
        executables=("cursor",),
        evidence="用户规则保存在应用设置里，没有可写的文件入口",
    ),
    "doubao": AgentProfile(
        id="doubao",
        name="豆包桌面版",
        level=LEVEL_DETECT,
        kind="chat",
        locations=(
            Location("doubao", "{appdata}/Doubao", "windows"),
            Location("doubao", "{home}/Library/Application Support/Doubao", "macos"),
        ),
        evidence="个性化设置保存在云端账号，本地没有规则入口",
    ),
    "cc-switch": AgentProfile(
        id="cc-switch",
        name="CC Switch",
        level=LEVEL_DETECT,
        kind="manager",
        locations=(_home(".cc-switch", "cc-switch"),),
        skills=("skills",),
        manages=(
            "Claude/Codex 的提供商与 API 设置（例如 settings.json 中的 env）",
            "skills 目录（可能以链接方式接管 ~/.claude/skills）",
        ),
        evidence="管理类工具：ai-config 与其共存，不触碰它接管的字段与链接",
    ),
}

#: Codex and Claude keep their historical top-level ``codex``/``claude`` keys in
#: device.json; every other agent instance is declared under ``agents``.
LEGACY_INSTANCES = ("codex", "claude")

INSTANCE_ID = re.compile(r"[a-z0-9][a-z0-9_-]*")


def profile_for_instance(instance_id: str) -> AgentProfile | None:
    """The profile that declares ``instance_id`` (``workbuddy-ai`` -> workbuddy)."""
    if instance_id in PROFILES and instance_id != GENERIC:
        return PROFILES[instance_id]
    for profile in PROFILES.values():
        if instance_id in profile.instances:
            return profile
    return None


def display_name(instance_id: str) -> str:
    profile = profile_for_instance(instance_id)
    if profile is None:
        return instance_id
    if len(profile.instances) > 1 and instance_id != profile.instances[0]:
        return f"{profile.name}（{instance_id}）"
    return profile.name


def label(instance_id: str) -> str:
    """Name plus the id a user types in commands, without repeating the id."""
    name = display_name(instance_id)
    return name if instance_id in name else f"{name}（{instance_id}）"


# --------------------------------------------------------------------------
# Host environment
# --------------------------------------------------------------------------

def _system_name(value: str | None = None) -> str:
    system = (value or platform.system()).casefold()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    return system or "unknown"


@dataclass(frozen=True)
class HostEnv:
    """Every host fact detection may depend on, injectable for sandboxes."""

    home: Path
    system: str
    appdata: Path | None
    localappdata: Path | None
    xdg_config: Path
    environ: Mapping[str, str]
    which: Callable[[str], str | None]

    @classmethod
    def current(cls) -> "HostEnv":
        environ = os.environ
        system = _system_name()
        home = Path.home()
        appdata = localappdata = None
        if system == "windows":
            appdata = Path(environ["APPDATA"]) if environ.get("APPDATA") else home / "AppData" / "Roaming"
            localappdata = Path(environ["LOCALAPPDATA"]) if environ.get("LOCALAPPDATA") else home / "AppData" / "Local"
        xdg = Path(environ["XDG_CONFIG_HOME"]) if environ.get("XDG_CONFIG_HOME") else home / ".config"
        return cls(home, system, appdata, localappdata, xdg, environ, lambda name: shutil.which(name))

    @classmethod
    def for_home(
        cls,
        home: Path,
        *,
        system: str | None = None,
        environ: Mapping[str, str] | None = None,
        which: Callable[[str], str | None] | None = None,
    ) -> "HostEnv":
        """Derive every location from ``home`` so nothing outside it is consulted.

        Root override variables (``CODEX_HOME`` ...) are still read from
        ``environ``, which defaults to the live process environment.
        """
        resolved = _system_name(system) if system else _system_name()
        appdata = home / "AppData" / "Roaming" if resolved == "windows" else None
        localappdata = home / "AppData" / "Local" if resolved == "windows" else None
        return cls(
            home,
            resolved,
            appdata,
            localappdata,
            home / ".config",
            os.environ if environ is None else environ,
            which or (lambda name: shutil.which(name)),
        )

    def expand(self, template: str) -> Path | None:
        values = {
            "{home}": self.home,
            "{appdata}": self.appdata,
            "{localappdata}": self.localappdata,
            "{xdg_config}": self.xdg_config,
        }
        for placeholder, value in values.items():
            if placeholder in template:
                if value is None:
                    return None
                template = template.replace(placeholder, str(value))
        return Path(template)


@dataclass(frozen=True)
class DetectedInstance:
    instance: str
    profile: AgentProfile
    root: Path
    origin: str
    exists: bool
    executable: str | None

    @property
    def installed(self) -> bool:
        return self.exists or bool(self.executable)


def detect_instances(host: HostEnv, *, profiles: Iterable[AgentProfile] | None = None) -> list[DetectedInstance]:
    """Locate every known agent instance.  Read-only: nothing is created."""
    result: list[DetectedInstance] = []
    for profile in profiles or PROFILES.values():
        if profile.id == GENERIC:
            continue
        executable = next((found for found in (host.which(name) for name in profile.executables) if found), None)
        for instance in profile.instances:
            candidates = [
                path for path in (
                    host.expand(location.template)
                    for location in profile.locations
                    if location.instance == instance and location.system in {"*", host.system}
                )
                if path is not None
            ]
            root: Path | None = None
            origin = "默认位置"
            if instance == profile.instances[0]:
                for variable in profile.root_env:
                    value = host.environ.get(variable)
                    if value:
                        root, origin = Path(value).expanduser(), f"环境变量 {variable}"
                        break
            if root is None:
                root = next((path for path in candidates if path.is_dir()), candidates[0] if candidates else None)
            if root is None:
                continue
            exists = root.is_dir()
            # An executable belongs to the first instance; the others are only
            # installed when their own directory exists.
            result.append(DetectedInstance(
                instance,
                profile,
                root,
                origin,
                exists,
                executable if instance == profile.instances[0] else None,
            ))
    return result


# --------------------------------------------------------------------------
# Instances configured on this device
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentInstance:
    id: str
    profile: AgentProfile
    root: Path
    topics: tuple[str, ...]
    rules: RulesEntry | None
    legacy: bool


@dataclass(frozen=True)
class RulesTarget:
    instance: str
    path: Path
    mode: str
    kind: str


def _topics(values: Iterable[str] | None, profile: AgentProfile) -> tuple[str, ...]:
    from .config import SHARED_RULE_TOPICS

    chosen = set(values) if values is not None else set(profile.topics or SHARED_RULE_TOPICS)
    # Rendering always follows the canonical topic order, whatever order the
    # device listed them in, so two devices with the same selection agree.
    return tuple(topic for topic in SHARED_RULE_TOPICS if topic in chosen)


def agent_instances(raw: Mapping[str, Any]) -> list[AgentInstance]:
    """Every agent instance this device manages, in a stable order."""
    from .config import absolute

    instances: list[AgentInstance] = []
    for legacy in LEGACY_INSTANCES:
        if raw.get(legacy):
            profile = PROFILES[legacy]
            instances.append(AgentInstance(legacy, profile, absolute(raw[legacy]), _topics(None, profile), profile.rules, True))
    declared = raw.get("agents") or {}
    for instance_id in sorted(declared):
        spec = declared[instance_id]
        profile = PROFILES[spec["profile"]] if spec.get("profile") else profile_for_instance(instance_id)
        if profile is None:
            raise ValueError(f"Unknown agent: {instance_id}")
        rules = profile.rules
        if profile.id == GENERIC:
            declared_rules = spec.get("rules") or {}
            rules = RulesEntry(str(declared_rules.get("mode")), str(declared_rules.get("path")))
        instances.append(AgentInstance(
            instance_id,
            profile,
            absolute(spec["root"]),
            _topics(spec.get("topics"), profile),
            rules,
            False,
        ))
    return instances


def instance_ids(raw: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(instance.id for instance in agent_instances(raw))


def rules_target(instance: AgentInstance) -> RulesTarget | None:
    """The one file ai-config writes for this instance, or ``None``.

    ``None`` means the entry cannot be resolved yet (for example TRAE before its
    first global rule exists).  Nothing is ever created to make an entry appear.
    """
    entry = instance.rules
    if entry is None:
        return None
    if entry.mode == MODE_BLOCK:
        return RulesTarget(instance.id, instance.root / entry.path, MODE_BLOCK, KIND_BLOCK)
    if entry.mode == MODE_FILE:
        return RulesTarget(instance.id, instance.root / entry.path, MODE_FILE, KIND_FILE)
    if entry.mode == MODE_PROBE_TRAE:
        directory = instance.root / "user_rules"
        if directory.is_dir() and not directory.is_symlink():
            return RulesTarget(instance.id, directory / OWNED_FILE_NAME, MODE_FILE, KIND_FILE)
        for name in ("user_rules", "user_rules.md"):
            single = instance.root / name
            if single.is_file() and not single.is_symlink():
                return RulesTarget(instance.id, single, MODE_BLOCK, KIND_BLOCK)
        return None
    raise ValueError(f"Unknown rules mode: {entry.mode}")


def unresolved_reason(instance: AgentInstance) -> str | None:
    """Why an instance has no writable entry right now, in Chinese."""
    if not instance.legacy and not instance.root.is_dir():
        return f"{display_name(instance.id)} 的配置目录不存在：{instance.root}（未安装或尚未启动过；不会自动创建）"
    if instance.rules is not None and instance.rules.mode == MODE_PROBE_TRAE and rules_target(instance) is None:
        return "未找到 TRAE 全局规则位置：请先在 TRAE 设置 → 规则中创建一次全局规则，再运行同步"
    return None


def managed_targets(raw: Mapping[str, Any]) -> list[tuple[AgentInstance, RulesTarget]]:
    """Instances whose rules entry can be written now.

    Codex and Claude keep their historical behaviour (the entry is written even
    when the root was never created); every other agent is only touched when
    its own directory already exists.
    """
    result: list[tuple[AgentInstance, RulesTarget]] = []
    for instance in agent_instances(raw):
        if unresolved_reason(instance) is not None:
            continue
        target = rules_target(instance)
        if target is not None:
            result.append((instance, target))
    return result


# --------------------------------------------------------------------------
# Validation of the device ``agents`` declaration
# --------------------------------------------------------------------------

def matches(relative: str, patterns: Iterable[str]) -> bool:
    """Whether a root-relative path (or any of its parents) matches a pattern."""
    normalized = relative.replace("\\", "/").strip("/")
    if not normalized:
        return False
    parts = normalized.split("/")
    prefixes = ["/".join(parts[: index + 1]) for index in range(len(parts))]
    names = [part.casefold() for part in parts]
    for pattern in patterns:
        lowered = pattern.casefold()
        for prefix in prefixes:
            if fnmatch.fnmatchcase(prefix.casefold(), lowered):
                return True
        # A bare name pattern also matches that name at any depth.
        if "/" not in lowered and any(fnmatch.fnmatchcase(name, lowered) for name in names):
            return True
    return False


def is_sensitive(profile: AgentProfile, relative: str) -> bool:
    return matches(relative, (*COMMON_SENSITIVE, *profile.sensitive))


def _validate_relative_markdown(value: Any, instance_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"agents.{instance_id}.rules.path must be a relative Markdown path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", normalized) or ".." in path.parts or any(part in {"", "."} for part in normalized.split("/")):
        raise ValueError(f"agents.{instance_id}.rules.path must stay inside the agent root: {value}")
    if path.suffix.casefold() != ".md":
        raise ValueError(f"agents.{instance_id}.rules.path must be a .md file: {value}")
    if matches(normalized, COMMON_SENSITIVE):
        raise ValueError(f"agents.{instance_id}.rules.path names a protected file: {value}")
    return normalized


def validate_agents(raw: Mapping[str, Any]) -> None:
    """Strict validation of the optional ``agents`` object in device.json."""
    from .config import SHARED_RULE_TOPICS

    declared = raw.get("agents")
    if declared is None:
        return
    if not isinstance(declared, dict):
        raise ValueError("agents must be an object of agent instances")
    for instance_id, spec in declared.items():
        if not isinstance(instance_id, str) or not INSTANCE_ID.fullmatch(instance_id):
            raise ValueError(f"Invalid agent instance id: {instance_id}")
        if instance_id in LEGACY_INSTANCES:
            raise ValueError(f"{instance_id} is configured with the top-level '{instance_id}' field, not under agents")
        if not isinstance(spec, dict):
            raise ValueError(f"agents.{instance_id} must be an object")
        unknown = sorted(set(spec) - {"profile", "root", "topics", "rules"})
        if unknown:
            raise ValueError(f"agents.{instance_id} has unsupported fields: {', '.join(unknown)}")
        if not isinstance(spec.get("root"), str) or not spec["root"].strip():
            raise ValueError(f"agents.{instance_id}.root must be a path string")
        profile_id = spec.get("profile")
        if profile_id is not None:
            if not isinstance(profile_id, str) or profile_id not in PROFILES:
                raise ValueError(f"agents.{instance_id}.profile is not a known agent: {profile_id}")
            profile = PROFILES[profile_id]
        else:
            profile = profile_for_instance(instance_id)
            if profile is None:
                raise ValueError(f"Unknown agent: {instance_id}; set profile to a known agent or '{GENERIC}'")
        if not profile.writable:
            raise ValueError(f"{profile.name} can only be detected; ai-config does not write to it")
        topics = spec.get("topics")
        if topics is not None:
            if not isinstance(topics, list) or not topics or any(not isinstance(item, str) for item in topics) or len(topics) != len(set(topics)):
                raise ValueError(f"agents.{instance_id}.topics must be a non-empty list of unique topic names")
            unknown_topics = sorted(set(topics) - set(SHARED_RULE_TOPICS))
            if unknown_topics:
                raise ValueError(f"agents.{instance_id}.topics has unknown topics: {', '.join(unknown_topics)}")
        rules = spec.get("rules")
        if profile.id == GENERIC:
            if not isinstance(rules, dict) or set(rules) - {"mode", "path"}:
                raise ValueError(f"agents.{instance_id}.rules must declare mode and path")
            if rules.get("mode") not in DECLARABLE_MODES:
                raise ValueError(f"agents.{instance_id}.rules.mode must be one of: {', '.join(DECLARABLE_MODES)}")
            _validate_relative_markdown(rules.get("path"), instance_id)
        elif rules is not None:
            raise ValueError(f"agents.{instance_id}.rules can only be declared for the '{GENERIC}' profile")
