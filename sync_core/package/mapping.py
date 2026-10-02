"""Resolve portable package identifiers to receiver-local targets without writes."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from .. import agents
from ..config import (
    SHARED_CLAUDE_KEYS,
    SHARED_CODEX_KEYS,
    SHARED_RULE_TOPICS,
    absolute as config_absolute,
    validate as validate_device_config,
)
from ..diff_view import is_sensitive_value
from .check import CheckedPackage


@dataclass(frozen=True)
class AgentCandidate:
    instance_id: str
    profile_id: str
    root: Path
    installed: bool
    configured: bool
    origin: str

    def public_data(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "profile_id": self.profile_id,
            "root": str(self.root),
            "installed": self.installed,
            "configured": self.configured,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class PackageMappingItem:
    key: str
    logical_source: str
    storage_path: Path | None
    target_path: Path | None
    agent_instance: str | None
    profile_id: str | None
    status: str
    detail: str
    candidates: tuple[AgentCandidate, ...] = ()

    def public_data(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "logical_source": self.logical_source,
            "storage_path": str(self.storage_path) if self.storage_path else None,
            "target_path": str(self.target_path) if self.target_path else None,
            "agent_instance": self.agent_instance,
            "profile_id": self.profile_id,
            "status": self.status,
            "detail": self.detail,
            "candidates": [candidate.public_data() for candidate in self.candidates],
        }


@dataclass(frozen=True)
class PackageMappingPlan:
    status: str
    items: tuple[PackageMappingItem, ...]
    can_save_to_store: bool
    can_apply_to_agents: bool
    proposed_device_config: Mapping[str, Any] | None = field(default=None, repr=False)

    def public_data(self) -> dict[str, Any]:
        proposal = None
        if self.proposed_device_config is not None:
            proposal = {
                "preserves_receiver_identity": True,
                "agent_instances": [
                    {
                        "instance_id": item.agent_instance,
                        "profile_id": item.profile_id,
                        "root": str(item.target_path),
                    }
                    for item in self.items
                    if item.logical_source == "agent://shared/declarations.json"
                    and item.status in {"mapped", "already_configured"}
                    and item.agent_instance is not None
                    and item.target_path is not None
                ],
                "shared_setting_fields": [
                    {"profile_id": item.profile_id, "logical_source": item.logical_source}
                    for item in self.items
                    if item.profile_id in {"codex", "claude"}
                    and item.logical_source.startswith("settings://")
                    and item.status == "mapped"
                ],
            }
        return {
            "status": self.status,
            "can_save_to_store": self.can_save_to_store,
            "can_apply_to_agents": self.can_apply_to_agents,
            "items": [item.public_data() for item in self.items],
            "proposed_device_config_preview": proposal,
        }


class PackageMappingError(ValueError):
    """The checked package cannot be translated into receiver-local paths."""


def _segments(uri: str) -> tuple[str, str, list[str]]:
    try:
        parsed = urlsplit(uri)
        parts = [unquote(segment, errors="strict") for segment in parsed.path.lstrip("/").split("/")]
    except (UnicodeDecodeError, ValueError) as error:
        raise PackageMappingError("Package logical source is malformed") from error
    if not parsed.netloc or not parts or any(part in {"", ".", ".."} or "/" in part or "\\" in part for part in parts):
        raise PackageMappingError("Package logical source contains an unsafe path")
    return parsed.scheme, parsed.netloc, parts


def _strict_json(content: bytes) -> Any:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PackageMappingError(f"Package declaration contains duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise PackageMappingError("Package declaration is not valid UTF-8 JSON") from error


def _safe_destination(root: Path, relative: Path) -> Path:
    destination = root / relative
    current = destination
    while True:
        if current.is_symlink() or bool(getattr(current, "is_junction", lambda: False)()):
            raise PackageMappingError("Receiver destination contains a link or junction")
        if current == root:
            break
        current = current.parent
    for parent in root.parents:
        if parent.is_symlink() or bool(getattr(parent, "is_junction", lambda: False)()):
            raise PackageMappingError("Receiver configuration store has a link or junction in its path")
    if destination.exists() and not destination.is_file():
        raise PackageMappingError("Receiver destination exists but is not a regular file")
    return destination


def _configured_candidates(raw: Mapping[str, Any], profile_id: str) -> list[AgentCandidate]:
    result: list[AgentCandidate] = []
    if profile_id in agents.LEGACY_INSTANCES:
        value = raw.get(profile_id)
        if isinstance(value, str) and value:
            try:
                root = Path(value).expanduser()
                if not root.is_absolute():
                    raise PackageMappingError("Configured Agent root must be an absolute local path")
                root = config_absolute(root)
                result.append(AgentCandidate(profile_id, profile_id, root, root.is_dir(), True, "本机现有设备配置"))
            except (OSError, ValueError) as error:
                raise PackageMappingError("Configured Agent root is not a safe local path") from error
    declarations = raw.get("agents", {})
    if isinstance(declarations, Mapping):
        for instance_id, specification in declarations.items():
            if not isinstance(instance_id, str) or not isinstance(specification, Mapping):
                continue
            declared_profile = specification.get("profile")
            profile = agents.PROFILES.get(declared_profile) if isinstance(declared_profile, str) else agents.profile_for_instance(instance_id)
            if profile is None or profile.id != profile_id:
                continue
            root_value = specification.get("root")
            if not isinstance(root_value, str) or not root_value:
                continue
            try:
                root = Path(root_value).expanduser()
                if not root.is_absolute():
                    raise PackageMappingError("Configured Agent root must be an absolute local path")
                root = config_absolute(root)
                result.append(AgentCandidate(instance_id, profile_id, root, root.is_dir(), True, "本机现有设备配置"))
            except (OSError, ValueError) as error:
                raise PackageMappingError("Configured Agent root is not a safe local path") from error
    return result


def _candidate_instances(
    raw: Mapping[str, Any],
    profile_id: str,
    host: agents.HostEnv,
) -> tuple[AgentCandidate, ...]:
    configured = _configured_candidates(raw, profile_id)
    if configured:
        return tuple(sorted(configured, key=lambda candidate: candidate.instance_id))
    profile = agents.PROFILES.get(profile_id)
    if profile is None or profile_id == agents.GENERIC:
        return ()
    found = agents.detect_instances(host, profiles=(profile,))
    candidates: list[AgentCandidate] = []
    for item in found:
        try:
            root = config_absolute(item.root.expanduser())
        except (OSError, ValueError):
            continue
        candidates.append(AgentCandidate(
            item.instance,
            profile_id,
            root,
            item.installed,
            False,
            item.origin,
        ))
    return tuple(sorted(candidates, key=lambda candidate: candidate.instance_id))


def _select_candidate(
    *,
    key: str,
    profile_id: str,
    candidates: tuple[AgentCandidate, ...],
    selections: Mapping[str, str],
) -> tuple[AgentCandidate | None, str]:
    if not candidates:
        return None, "needs_setup"
    selected_id = selections.get(key)
    if selected_id is not None:
        selected = next((item for item in candidates if item.instance_id == selected_id), None)
        if selected is None:
            return None, "needs_selection"
        return selected, "mapped" if selected.installed else "not_installed"
    installed = [item for item in candidates if item.installed]
    if len(installed) == 1:
        return installed[0], "mapped"
    if not installed and len(candidates) == 1:
        return candidates[0], "not_installed"
    return None, "needs_selection"


def _declaration_items(package: CheckedPackage) -> list[tuple[str, str, dict[str, Any]]]:
    result: list[tuple[str, str, dict[str, Any]]] = []
    seen: dict[str, int] = {}
    for entry in package.manifest["entries"]:
        if entry["data_type"] != "agent_declaration" or not entry["logical_source"].endswith("/declarations.json"):
            continue
        source_scheme, source_authority, source_parts = _segments(entry["logical_source"])
        if source_scheme != "agent" or source_authority != "shared" or source_parts != ["declarations.json"] or entry["adapter_id"] != "agent_declaration":
            raise PackageMappingError("Agent declaration URI or adapter is unsupported")
        value = _strict_json(package.payloads[entry["object_path"]])
        if not isinstance(value, dict) or set(value) != {"instances"} or not isinstance(value["instances"], list):
            raise PackageMappingError("Agent declarations have an unsupported shape")
        for specification in value["instances"]:
            if not isinstance(specification, dict) or set(specification) - {"profile", "topics", "rules"}:
                raise PackageMappingError("Agent declaration contains an unsupported field")
            profile_id = specification.get("profile")
            profile = agents.PROFILES.get(profile_id) if isinstance(profile_id, str) else None
            if profile is None or not profile.writable:
                raise PackageMappingError("Agent declaration references an unsupported profile")
            topics = specification.get("topics")
            if "topics" in specification and (
                not isinstance(topics, list)
                or not topics
                or any(not isinstance(topic, str) or topic not in SHARED_RULE_TOPICS for topic in topics)
                or len(topics) != len(set(topics))
            ):
                raise PackageMappingError("Agent declaration has an unsupported rule topic selection")
            if "rules" in specification and profile.id != agents.GENERIC:
                raise PackageMappingError("Only a custom agent may declare a relative rule entry")
            probe = {"profile": profile_id, "root": str(Path.cwd() / "portable-target"), **specification}
            try:
                agents.validate_agents({"agents": {"portable-target": probe}})
            except (TypeError, ValueError) as error:
                raise PackageMappingError("Agent declaration contains an unsafe target-relative path") from error
            probe = {"profile": profile_id, "root": str(Path.cwd() / "portable-target"), **specification}
            try:
                agents.validate_agents({"agents": {"portable-target": probe}})
            except (TypeError, ValueError) as error:
                raise PackageMappingError("Agent declaration contains an unsafe target-relative path") from error
            seen[profile_id] = seen.get(profile_id, 0) + 1
            key = f"{profile_id}:{seen[profile_id]}"
            result.append((key, profile_id, specification))
    return result


def plan_package_mappings(
    package: CheckedPackage,
    *,
    store_root: Path | None,
    device_config: Mapping[str, Any] | None,
    host: agents.HostEnv | None = None,
    selections: Mapping[str, str] | None = None,
) -> PackageMappingPlan:
    """Preview portable entry destinations and receiver config without writes.

    ``selections`` maps a stable choice key (for example ``workbuddy:1``) to an
    instance id from that row's offered candidates. Arbitrary filesystem paths
    are never accepted from the package or selection map.
    """
    if not package.importable:
        raise PackageMappingError("Package has an unsupported adapter and cannot be mapped for import")
    raw = dict(device_config or {})
    if device_config is not None:
        try:
            validate_device_config(raw)
        except (TypeError, ValueError) as error:
            raise PackageMappingError("Receiver device configuration is invalid") from error
    local_host = host or agents.HostEnv.current()
    choices = selections or {}
    target_store = Path(store_root).expanduser().absolute() if store_root is not None else None
    store_ready = target_store is not None and target_store.is_dir()
    items: list[PackageMappingItem] = []
    proposed = deepcopy(raw) if device_config is not None else None
    if proposed is not None:
        proposed.setdefault("agents", {})
        proposed["agents"] = deepcopy(proposed["agents"])
    assigned_instances: set[str] = set()
    extension_names: dict[str, bytes] = {}

    for entry in package.manifest["entries"]:
        logical = entry["logical_source"]
        scheme, authority, parts = _segments(logical)
        content = package.payloads[entry["object_path"]]
        if entry["data_type"] in {"skill_file", "mcp_config", "memory_snapshot", "handoff_record"}:
            from .extensions import validate_extension, mcp_dependencies
            kind, profile_id, extension_parts = validate_extension(logical, entry["data_type"], entry["adapter_id"], content)
            relative_name = "/".join([kind, profile_id, *extension_parts])
            if relative_name in extension_names:
                raise PackageMappingError("扩展来源映射到重复目标。")
            extension_names[relative_name] = content
            storage = _safe_destination(target_store, Path("portable") / kind / profile_id / Path(*extension_parts)) if target_store else None
            candidates = _candidate_instances(raw, profile_id, local_host) if kind in {"skills", "mcp"} else ()
            selected, status = _select_candidate(key=profile_id, profile_id=profile_id, candidates=candidates, selections=choices) if candidates else (None, "mapped")
            target = None
            detail = "保存配置库；记忆与交接须重新选择本机项目，仅作参考，不声明已完整接续"
            if selected and status == "mapped":
                relative = Path("skills") / Path(*extension_parts) if kind == "skills" else Path("config.toml")
                try:
                    target = _safe_destination(selected.root, relative)
                except PackageMappingError:
                    detail = "目标含链接或其他管理工具接管；默认保留，仅保存配置库"
                else:
                    detail = "技能复制部署；不执行技能脚本" if kind == "skills" else "MCP 保存需要明确确认命令；保存不等于连接成功"
                    if kind == "mcp":
                        missing = mcp_dependencies(content)
                        if missing:
                            target = None
                            detail = "仅保存配置库；目标依赖缺失：" + "、".join(missing)
            if storage is None or not store_ready:
                status = "needs_setup"
            elif target is None:
                status = "mapped"
            items.append(PackageMappingItem(profile_id, logical, storage, target, selected.instance_id if selected else None, profile_id, status, detail, candidates))
            continue
        if scheme == "agent" and authority == "shared" and entry["data_type"] == "rule_file":
            if entry["adapter_id"] != "shared_rules":
                items.append(PackageMappingItem(logical, logical, None, None, None, None, "unsupported", "规则条目适配器声明不匹配"))
                continue
            if len(parts) != 2 or parts[0] != "common" or parts[1] not in {f"{topic}.md" for topic in SHARED_RULE_TOPICS}:
                items.append(PackageMappingItem(logical, logical, None, None, None, None, "unsupported", "规则来源不在受支持的 shared topic 清单中"))
                continue
            target = _safe_destination(target_store, Path("common") / parts[1]) if target_store is not None else None
            if target is not None and store_ready:
                items.append(PackageMappingItem(logical, logical, target, target, None, None, "mapped", "写入接收端配置库；尚未应用到 Agent"))
            else:
                items.append(PackageMappingItem(logical, logical, target, target, None, None, "needs_setup", "请先选择或创建本机配置库"))
            continue

        if scheme == "settings" and entry["data_type"] == "shared_setting":
            profile_id = authority
            allowed = SHARED_CODEX_KEYS if profile_id == "codex" else SHARED_CLAUDE_KEYS if profile_id == "claude" else frozenset()
            if len(parts) != 2 or parts[0] != "main" or parts[1] not in allowed:
                items.append(PackageMappingItem(logical, logical, None, None, None, profile_id, "unsupported", "共享设置来源不在支持的 Agent／字段清单中"))
                continue
            try:
                value = _strict_json(content)
            except PackageMappingError:
                value = None
            expected_adapter = f"{profile_id}_settings"
            if not isinstance(value, dict) or set(value) != {parts[1]} or entry["adapter_id"] != expected_adapter:
                items.append(PackageMappingItem(logical, logical, None, None, None, profile_id, "unsupported", "设置条目与适配器声明不匹配"))
                continue
            setting_value = value[parts[1]]
            if (
                setting_value is None
                or isinstance(setting_value, (dict, list))
                or not isinstance(setting_value, (str, int, float, bool))
                or is_sensitive_value(parts[1], setting_value)
            ):
                items.append(PackageMappingItem(profile_id, logical, None, None, None, profile_id, "unsupported", "设置值不是允许的非敏感标量"))
                continue
            candidates = _candidate_instances(raw, profile_id, local_host)
            selected, status = _select_candidate(key=profile_id, profile_id=profile_id, candidates=candidates, selections=choices)
            storage_relative = Path("codex/config.toml") if profile_id == "codex" else Path("claude/settings.shared.json")
            storage = _safe_destination(target_store, storage_relative) if target_store is not None else None
            filename = "config.toml" if profile_id == "codex" else "settings.json"
            target = selected.root / filename if selected is not None else None
            if target is not None and (target.is_symlink() or bool(getattr(target, "is_junction", lambda: False)())):
                status = "unsupported"
                target = None
            if status == "mapped" and proposed is not None and selected is not None:
                if profile_id not in proposed:
                    proposed[profile_id] = str(selected.root)
                overrides = proposed.get(f"{profile_id}_overrides", {})
                if isinstance(overrides, Mapping) and parts[1] in overrides:
                    status = "conflict"
                else:
                    keys_field = f"{profile_id}_keys"
                    keys = list(proposed.get(keys_field, []))
                    if parts[1] not in keys:
                        keys.append(parts[1])
                    proposed[keys_field] = keys
            if status == "mapped" and (not store_ready or device_config is None):
                status = "needs_setup"
            detail = "映射到接收端 Agent 设置文件；值仍需经过冲突预览与事务应用"
            if status == "not_installed":
                detail = "可先保存到配置库；目标 Agent 未安装或目录不存在，当前不能标为已应用"
            elif status == "needs_selection":
                detail = "存在多个候选实例，请选择一个接收目标"
            elif status == "needs_setup":
                detail = "请先完成本机设置并选择配置库"
            elif status == "conflict":
                detail = "本机已有该字段的仅本机覆盖；保留现值，需在冲突步骤明确处理"
            elif status == "unsupported":
                detail = "目标设置路径受链接保护，不能安全写入"
            items.append(PackageMappingItem(profile_id, logical, storage, target, selected.instance_id if selected else None, profile_id, status, detail, candidates))
            continue

        if scheme == "agent" and authority == "shared" and parts == ["agents-registry.json"] and entry["data_type"] == "agent_declaration":
            if entry["adapter_id"] != "agent_declaration":
                items.append(PackageMappingItem(logical, logical, None, None, None, None, "unsupported", "Agent 登记适配器声明不匹配"))
                continue
            registry = _strict_json(content)
            if not isinstance(registry, dict) or any(
                profile not in agents.PROFILES
                or not agents.PROFILES[profile].writable
                or not isinstance(specification, dict)
                or set(specification) != {"topics"}
                or not isinstance(specification["topics"], list)
                or not specification["topics"]
                or any(not isinstance(topic, str) or topic not in SHARED_RULE_TOPICS for topic in specification["topics"])
                or len(specification["topics"]) != len(set(specification["topics"]))
                for profile, specification in registry.items()
            ):
                items.append(PackageMappingItem(logical, logical, None, None, None, None, "unsupported", "Agent 规则登记包含未知 profile"))
                continue
            storage = _safe_destination(target_store, Path("agents.toml")) if target_store is not None else None
            status = "mapped" if storage is not None and store_ready else "needs_setup"
            items.append(PackageMappingItem(logical, logical, storage, None, None, None, status, "仅保存为接收端规则范围登记；不改写 Agent 路径" if storage is not None and store_ready else "请先选择本机配置库"))
            continue

        if scheme == "agent" and authority == "shared" and parts == ["declarations.json"] and entry["data_type"] == "agent_declaration":
            continue

        items.append(PackageMappingItem(logical, logical, None, None, None, None, "unsupported", "当前客户端没有此逻辑来源的目标适配器"))

    for key, profile_id, specification in _declaration_items(package):
        candidates = _candidate_instances(raw, profile_id, local_host)
        selected, status = _select_candidate(key=key, profile_id=profile_id, candidates=candidates, selections=choices)
        target = selected.root if selected is not None else None
        detail = "Agent 实例可映射；只生成本机路径声明预览，不写入设备配置"
        if status == "not_installed":
            detail = "目标 Agent 未安装；声明不写入设备配置，受支持的规则仍可保存在配置库"
        elif status == "needs_selection":
            detail = "存在多个候选实例，请选择一个接收目标"
        elif status == "needs_setup":
            detail = "未找到该 Agent 的本机实例；请先安装或登记自定义实例"
        elif device_config is None and status == "mapped":
            status = "needs_setup"
            detail = "Agent 目录已识别；需先创建本机设备配置，保留本机设备身份后才能登记"
        elif status == "mapped" and selected is not None:
            if selected.instance_id in assigned_instances:
                status = "conflict"
                detail = "多个包内声明指向同一目标实例；请在冲突步骤分别选择"
            else:
                assigned_instances.add(selected.instance_id)
                configured = raw.get("agents", {})
                current = configured.get(selected.instance_id) if isinstance(configured, Mapping) else None
                if current is not None:
                    profile_value = current.get("profile") or agents.profile_for_instance(selected.instance_id)
                    try:
                        current_root = config_absolute(str(current.get("root", "")))
                    except (OSError, ValueError):
                        current_root = None
                    same = profile_value == profile_id and current_root == selected.root and all(
                        current.get(field) == specification.get(field)
                        for field in ("topics", "rules")
                        if field in specification
                    )
                    status = "already_configured" if same else "conflict"
                    detail = "接收端已有相同 Agent 声明，保留现有配置" if same else "接收端已有不同 Agent 声明；不得静默覆盖"
                elif proposed is not None:
                    target_spec: dict[str, Any] = {"profile": profile_id, "root": str(selected.root)}
                    for field_name in ("topics", "rules"):
                        if field_name in specification:
                            target_spec[field_name] = deepcopy(specification[field_name])
                    try:
                        agents.validate_agents({"agents": {selected.instance_id: target_spec}})
                    except (TypeError, ValueError):
                        status = "unsupported"
                        detail = "包中的相对规则声明不符合目标 Agent 的安全规则"
                    else:
                        proposed["agents"][selected.instance_id] = target_spec
        items.append(PackageMappingItem(key, "agent://shared/declarations.json", None, target, selected.instance_id if selected else None, profile_id, status, detail, candidates))

    from ..merge import validate_file_map
    try:
        validate_file_map(extension_names)
    except ValueError as error:
        raise PackageMappingError("扩展目标存在大小写／Unicode／目录碰撞。") from error
    items.sort(key=lambda item: item.key)
    statuses = {item.status for item in items}
    if statuses & {"unsupported", "conflict"}:
        plan_status = "blocked"
    elif "needs_selection" in statuses:
        plan_status = "needs_selection"
    elif "needs_setup" in statuses:
        plan_status = "needs_setup"
    elif "not_installed" in statuses:
        plan_status = "partial"
    else:
        plan_status = "ready"
    can_save = bool(target_store and store_ready) and all(
        item.storage_path is not None
        or (
            item.logical_source == "agent://shared/declarations.json"
            and item.status in {"mapped", "already_configured"}
            and proposed is not None
        )
        for item in items
    )
    can_apply = plan_status == "ready" and device_config is not None and all(
        item.status in {"mapped", "already_configured"} for item in items
    )
    return PackageMappingPlan(plan_status, tuple(items), can_save, can_apply, proposed)
