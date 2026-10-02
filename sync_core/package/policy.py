"""Allowlisted source collection policy for portable configuration packages.

Only explicitly supported store files and selected shared scalar settings are
read. Agent roots, device state, memory databases, auth files, caches and unknown
files are outside this module's read set by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import hashlib
import os
from pathlib import Path
import re
import tomllib
from typing import Any, Mapping
from urllib.parse import quote

from .. import agents
from ..config import (
    SHARED_CLAUDE_KEYS,
    SHARED_CODEX_KEYS,
    SHARED_RULE_TOPICS,
    selected_claude_keys,
    selected_codex_keys,
)
from ..diff_view import is_sensitive_value
from ..utils import SECRET
_LOCAL_PATH_PATTERNS = (
    re.compile(r"(?i)(?<![A-Za-z0-9])(?:[A-Z]:[\\/](?:Users|Documents and Settings|home|workspace|workspaces|Desktop)[\\/][^\s\"'`<>]+)"),
    re.compile(r"(?<![\w])/(?:Users|home|Volumes|mnt|workspace|workspaces)/[^\s\"'`<>]+"),
    re.compile(r"(?<![\w])~/(?:[^\s\"'`<>]+)"),
    re.compile(r"(?<![\w])\\\\[^\\/\s]+[\\/][^\\/\s]+(?:[\\/][^\s\"'`<>]+)?"),
)


@dataclass(frozen=True)
class PortableEntry:
    logical_source: str
    data_type: str
    adapter_id: str
    adapter_version: int
    content: bytes = field(repr=False)


@dataclass(frozen=True)
class PolicyIssue:
    logical_source: str
    category: str
    detail: str
    line_numbers: tuple[int, ...] = ()


@dataclass(frozen=True)
class CollectionReport:
    entries: tuple[PortableEntry, ...]
    exclusions: tuple[PolicyIssue, ...]
    unsupported: tuple[PolicyIssue, ...]
    review_required: tuple[PolicyIssue, ...]
    unclassified_top_level_count: int
    source_fingerprints: tuple[tuple[str, str], ...] = field(default=(), repr=False)

    @property
    def ready_without_review(self) -> bool:
        return bool(self.entries) and not self.review_required and not self.unsupported

    def public_summary(self) -> dict[str, Any]:
        """Return safe counters and logical source ids, never content or local paths."""
        return {
            "included": [entry.logical_source for entry in self.entries],
            "excluded": [
                {"logical_source": issue.logical_source, "category": issue.category}
                for issue in self.exclusions
            ],
            "unsupported": [
                {"logical_source": issue.logical_source, "category": issue.category, "detail": issue.detail}
                for issue in self.unsupported
            ],
            "review_required": [
                {
                    "logical_source": issue.logical_source,
                    "category": issue.category,
                    "detail": issue.detail,
                    "line_numbers": list(issue.line_numbers),
                }
                for issue in self.review_required
            ],
            "unclassified_top_level_count": self.unclassified_top_level_count,
            "ready_without_review": self.ready_without_review,
        }


def _logical_source(source: str) -> str:
    # Encode non-ASCII or otherwise reserved filename bytes; never put the local
    # store path in a package identifier.
    parts = source.split("/")
    return "agent://shared/" + "/".join(quote(part, safe="-._~") for part in parts)


def _path_is_safe(root: Path, target: Path) -> bool:
    try:
        resolved_root = root.resolve(strict=True)
        resolved_target = target.resolve(strict=True)
        if not resolved_root.is_dir() or not resolved_target.is_file():
            return False
        resolved_target.relative_to(resolved_root)
    except (OSError, ValueError):
        return False
    current = target
    while current != root:
        if current.is_symlink() or bool(getattr(current, "is_junction", lambda: False)()):
            return False
        parent = current.parent
        if parent == current:
            return False
        current = parent
    return not root.is_symlink()


def _stable_read(root: Path, relative: str, fingerprints: dict[str, str]) -> bytes | None:
    target = root / relative
    if not _path_is_safe(root, target):
        return None
    before = target.stat()
    content = target.read_bytes()
    after = target.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise OSError("source changed while being read")
    fingerprints[_logical_source(relative)] = hashlib.sha256(content).hexdigest()
    return content


def _local_path_lines(text: str, local_roots: tuple[str, ...]) -> tuple[int, ...]:
    needles = tuple(
        normalized
        for value in local_roots
        if value
        for normalized in {value.casefold(), value.replace("\\", "/").casefold(), value.replace("/", "\\").casefold()}
        if len(normalized) >= 4
    )
    matched: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        folded = line.casefold()
        if any(needle in folded for needle in needles) or any(pattern.search(line) for pattern in _LOCAL_PATH_PATTERNS):
            matched.append(number)
    return tuple(matched)


def _text_policy_issue(
    source: str,
    content: bytes,
    *,
    local_roots: tuple[str, ...],
) -> PolicyIssue | None:
    logical = _logical_source(source)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return PolicyIssue(logical, "unsupported", "来源不是 UTF-8 文本")
    if SECRET.search(text):
        return PolicyIssue(logical, "sensitive", "疑似包含凭据；正文未纳入包")
    path_lines = _local_path_lines(text, local_roots)
    if path_lines:
        return PolicyIssue(logical, "local_only", "发现需要人工转换或删除的本机路径；未自动替换", path_lines)
    return None


def _local_roots(config: Mapping[str, Any]) -> tuple[str, ...]:
    values = [str(Path.home())]
    for key in ("state_dir", "memory_repo", "config_repo", "codex", "claude", "codex_memory"):
        item = config.get(key)
        if isinstance(item, str) and item:
            values.append(os.path.expandvars(os.path.expanduser(item)))
    for key in ("projects",):
        records = config.get(key, {})
        if isinstance(records, Mapping):
            values.extend(value for value in records.values() if isinstance(value, str) and value)
    for key in ("additional_sources", "memories"):
        records = config.get(key, [])
        if isinstance(records, list):
            values.extend(
                item["path"] for item in records
                if isinstance(item, Mapping) and isinstance(item.get("path"), str) and item["path"]
            )
    return tuple(dict.fromkeys(values))


def _add_text_file(
    root: Path,
    relative: str,
    *,
    data_type: str,
    adapter_id: str,
    local_roots: tuple[str, ...],
    entries: list[PortableEntry],
    exclusions: list[PolicyIssue],
    unsupported: list[PolicyIssue],
    review_required: list[PolicyIssue],
    fingerprints: dict[str, str],
) -> None:
    source = _logical_source(relative)
    try:
        content = _stable_read(root, relative, fingerprints)
    except OSError:
        unsupported.append(PolicyIssue(source, "unsupported", "来源读取失败或在采集时发生变化"))
        return
    if content is None:
        if (root / relative).exists() or (root / relative).is_symlink():
            exclusions.append(PolicyIssue(source, "protected", "路径不是普通的本机文件；未读取正文"))
        else:
            unsupported.append(PolicyIssue(source, "unsupported", "可选来源文件不存在"))
        return
    issue = _text_policy_issue(relative, content, local_roots=local_roots)
    if issue:
        if issue.category == "local_only":
            review_required.append(issue)
        else:
            exclusions.append(issue)
        return
    entries.append(PortableEntry(source, data_type, adapter_id, 1, content))


def _selected_settings(
    config: Mapping[str, Any],
    store_root: Path,
    *,
    tool: str,
    keys: tuple[str, ...],
    entries: list[PortableEntry],
    exclusions: list[PolicyIssue],
    unsupported: list[PolicyIssue],
    review_required: list[PolicyIssue],
    local_roots: tuple[str, ...],
    fingerprints: dict[str, str],
) -> None:
    if not keys:
        return
    relative = "codex/config.toml" if tool == "codex" else "claude/settings.shared.json"
    logical_prefix = f"settings://{tool}/main"
    try:
        content = _stable_read(store_root, relative, fingerprints)
    except OSError:
        content = None
    if content is None:
        unsupported.append(PolicyIssue(f"{logical_prefix}/settings", "unsupported", "共享设置来源缺失或无法安全读取"))
        return
    issue = _text_policy_issue(relative, content, local_roots=local_roots)
    if issue:
        if issue.category == "local_only":
            review_required.append(issue)
        else:
            exclusions.append(issue)
        return
    try:
        document = tomllib.loads(content.decode("utf-8")) if tool == "codex" else json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError):
        unsupported.append(PolicyIssue(f"{logical_prefix}/settings", "unsupported", "共享设置格式无法解析"))
        return
    if not isinstance(document, Mapping):
        unsupported.append(PolicyIssue(f"{logical_prefix}/settings", "unsupported", "共享设置必须是对象"))
        return
    allowed = SHARED_CODEX_KEYS if tool == "codex" else SHARED_CLAUDE_KEYS
    for key in keys:
        field_source = f"{logical_prefix}/{quote(key, safe='-._~')}"
        if key not in allowed or key not in document:
            unsupported.append(PolicyIssue(field_source, "unsupported", "字段不在当前共享 allowlist 中或来源缺失"))
            continue
        value = document[key]
        if isinstance(value, (dict, list)) or is_sensitive_value(key, value):
            exclusions.append(PolicyIssue(field_source, "sensitive", "字段值不符合共享设置安全策略；未纳入包"))
            continue
        serialized = json.dumps({key: value}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        issue = _text_policy_issue(f"{tool}/{key}", serialized, local_roots=local_roots)
        if issue:
            if issue.category == "local_only":
                review_required.append(PolicyIssue(field_source, issue.category, issue.detail, issue.line_numbers))
            else:
                exclusions.append(PolicyIssue(field_source, issue.category, issue.detail))
            continue
        entries.append(PortableEntry(field_source, "shared_setting", f"{tool}_settings", 1, serialized))


def _add_agent_declarations(
    config: Mapping[str, Any],
    entries: list[PortableEntry],
    exclusions: list[PolicyIssue],
    unsupported: list[PolicyIssue],
) -> None:
    from ..agents import validate_agents

    try:
        validate_agents(config)
    except (TypeError, ValueError):
        unsupported.append(PolicyIssue("agent://shared/declarations.json", "unsupported", "设备 Agent 声明无法安全转换"))
        return
    declarations = config.get("agents", {})
    if not isinstance(declarations, Mapping):
        return
    sanitized_instances: list[dict[str, Any]] = []
    for instance_id, specification in sorted(declarations.items()):
        profile_id = specification.get("profile")
        profile = agents.profile_for_instance(instance_id) if profile_id is None else agents.PROFILES.get(profile_id)
        if profile is None:
            unsupported.append(PolicyIssue("agent://shared/declarations.json", "unsupported", "声明对应的 Agent profile 未知"))
            return
        portable: dict[str, Any] = {"profile": profile.id}
        if "topics" in specification:
            portable["topics"] = sorted(specification["topics"])
        if "rules" in specification:
            portable["rules"] = dict(specification["rules"])
        sanitized_instances.append(portable)
    if not sanitized_instances:
        return
    source = "agent://shared/declarations.json"
    sanitized_instances.sort(key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=True))
    content = json.dumps(
        {"instances": sanitized_instances}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if SECRET.search(content.decode("utf-8")):
        exclusions.append(PolicyIssue(source, "sensitive", "声明字段疑似包含凭据；未纳入包"))
        return
    entries.append(PortableEntry(source, "agent_declaration", "agent_declaration", 1, content))


def _add_store_agent_registry(
    store_root: Path,
    entries: list[PortableEntry],
    exclusions: list[PolicyIssue],
    unsupported: list[PolicyIssue],
    fingerprints: dict[str, str],
) -> None:
    relative = "agents.toml"
    source = _logical_source(relative)
    try:
        content = _stable_read(store_root, relative, fingerprints)
    except OSError:
        content = None
    if content is None:
        candidate = store_root / relative
        if candidate.exists() or candidate.is_symlink():
            exclusions.append(PolicyIssue(source, "protected", "登记路径不是普通文件；未读取正文"))
        return
    issue = _text_policy_issue(relative, content, local_roots=())
    if issue:
        if issue.category == "sensitive":
            exclusions.append(issue)
        else:
            unsupported.append(issue)
        return
    try:
        parsed = tomllib.loads(content.decode("utf-8"))
        sanitized: dict[str, dict[str, list[str]]] = {}
        for profile_id, spec in parsed.items():
            if profile_id not in agents.PROFILES or not isinstance(spec, Mapping) or set(spec) != {"topics"}:
                raise ValueError("unsupported registry entry")
            topics = spec["topics"]
            if not isinstance(topics, list) or not topics or any(topic not in SHARED_RULE_TOPICS for topic in topics):
                raise ValueError("invalid topic selection")
            sanitized[profile_id] = {"topics": list(dict.fromkeys(topics))}
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, TypeError, ValueError):
        unsupported.append(PolicyIssue(source, "unsupported", "Agent 规则范围登记含不支持字段；未读取其他文件"))
        return
    canonical = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    entries.append(PortableEntry("agent://shared/agents-registry.json", "agent_declaration", "agent_declaration", 1, canonical))


def collect_portable_config(config: Mapping[str, Any], store_root: Path, *, extension_kinds: list[str] | None = None) -> CollectionReport:
    """Collect only explicit portable rule/settings/declaration sources.

    This function never traverses an agent root or recursively scans a store.
    Secret findings are omitted; local paths are omitted and reported by source
    plus line number for user review. Device-local overrides are not collected.
    """
    root = Path(store_root)
    entries: list[PortableEntry] = []
    exclusions: list[PolicyIssue] = []
    unsupported: list[PolicyIssue] = []
    review_required: list[PolicyIssue] = []
    source_fingerprints: dict[str, str] = {}
    local_roots = _local_roots(config)

    for topic in SHARED_RULE_TOPICS:
        _add_text_file(
            root,
            f"common/{topic}.md",
            data_type="rule_file",
            adapter_id="shared_rules",
            local_roots=local_roots,
            entries=entries,
            exclusions=exclusions,
            unsupported=unsupported,
            review_required=review_required,
            fingerprints=source_fingerprints,
        )
    _selected_settings(
        config,
        root,
        tool="codex",
        keys=selected_codex_keys(config),
        entries=entries,
        exclusions=exclusions,
        unsupported=unsupported,
        review_required=review_required,
        local_roots=local_roots,
        fingerprints=source_fingerprints,
    )
    _selected_settings(
        config,
        root,
        tool="claude",
        keys=selected_claude_keys(config),
        entries=entries,
        exclusions=exclusions,
        unsupported=unsupported,
        review_required=review_required,
        local_roots=local_roots,
        fingerprints=source_fingerprints,
    )
    _add_store_agent_registry(root, entries, exclusions, unsupported, source_fingerprints)
    _add_agent_declarations(config, entries, exclusions, unsupported)

    known_top_level = {"common", "codex", "claude", "agents.toml", "README.md", ".git", "portable"}
    try:
        unclassified_count = sum(1 for child in root.iterdir() if child.name not in known_top_level)
    except OSError:
        unclassified_count = 0
        unsupported.append(PolicyIssue("agent://shared/store", "unsupported", "无法读取配置库目录清单"))
    entries.sort(key=lambda item: item.logical_source)
    exclusions.sort(key=lambda item: item.logical_source)
    unsupported.sort(key=lambda item: item.logical_source)
    review_required.sort(key=lambda item: item.logical_source)
    report = CollectionReport(
        tuple(entries),
        tuple(exclusions),
        tuple(unsupported),
        tuple(review_required),
        unclassified_count,
        tuple(sorted(source_fingerprints.items())),
    )
    if extension_kinds:
        from .extensions import collect_extensions
        report = collect_extensions(root, report, extension_kinds)
    return report


def select_portable_sources(
    report: CollectionReport,
    selected_sources: list[str] | tuple[str, ...] | None = None,
) -> CollectionReport:
    """Narrow a collected report to explicit portable logical sources.

    Safe entries are selected by default. Review-required and unsupported
    sources remain visible but opt-in; selecting one keeps its blocker active.
    Every omitted candidate becomes an explicit non-deletion exclusion.
    """
    available = {
        item.logical_source
        for item in (*report.entries, *report.review_required, *report.unsupported)
    }
    selected = (
        {item.logical_source for item in report.entries}
        if selected_sources is None
        else set(selected_sources)
    )
    if selected_sources is not None and len(selected) != len(selected_sources):
        raise ValueError("Portable source selection contains duplicates")
    if selected - available:
        raise ValueError("Portable source selection contains unknown logical sources")
    omitted = sorted(available - selected)
    exclusions = [
        *report.exclusions,
        *(PolicyIssue(source, "user_excluded", "用户未选择导出此项") for source in omitted),
    ]
    fingerprints = tuple(
        (source, fingerprint)
        for source, fingerprint in report.source_fingerprints
        if source in selected
    )
    return CollectionReport(
        tuple(item for item in report.entries if item.logical_source in selected),
        tuple(sorted(exclusions, key=lambda item: item.logical_source)),
        tuple(item for item in report.unsupported if item.logical_source in selected),
        tuple(item for item in report.review_required if item.logical_source in selected),
        report.unclassified_top_level_count,
        fingerprints,
    )
