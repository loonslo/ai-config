"""Recoverable application of a reviewed offline package import plan."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import io
import json
from pathlib import Path
from types import SimpleNamespace
import uuid
import zipfile
from typing import Any, Mapping

from .. import agents
from ..config import validate as validate_device_config
from ..config_status import BEGIN, END, managed_block
from ..transaction import PlannedChanges, SyncBusyError, transaction, write_file
from ..utils import digest, read_bytes
from .check import MAX_ARCHIVE_BYTES, CheckedPackage, PackageCheckError, check_package
from .conflicts import (
    MAX_TARGET_BYTES,
    PackageConflictError,
    PackageConflictPlan,
    PackageTargetSnapshot,
    _file_bytes,
    _render_rules_block,
    inspect_package_targets,
    plan_package_conflicts,
)
from .mapping import PackageMappingError, PackageMappingPlan, plan_package_mappings


SUPPORTED_ADAPTERS = {
    "shared_rules": 1,
    "codex_settings": 1,
    "claude_settings": 1,
    "agent_declaration": 1,
    "skills_v1": 1,
    "mcp_v1": 1,
    "memory_portable_v1": 1,
    "handoff_portable_v1": 1,
}


class PackageImportError(RuntimeError):
    """The preview is stale, incomplete, or could not be safely applied."""


@dataclass(frozen=True)
class PackageImportPlan:
    plan_id: str
    status: str
    content_id: str
    source_name: str
    apply_to_agents: bool
    changed_file_count: int
    conflicts: PackageConflictPlan = field(repr=False)
    mapping: PackageMappingPlan = field(repr=False)
    targets: PackageTargetSnapshot = field(repr=False)
    changes: PlannedChanges = field(repr=False)
    package_path: Path = field(repr=False)
    baseline_path: Path = field(repr=False)
    backup_root: Path = field(repr=False)
    state_root: Path = field(repr=False)
    expected_package_id: str = field(repr=False)

    def public_data(self) -> dict[str, Any]:
        agent_selections = [
            {
                "key": item.key,
                "logical_source": item.logical_source,
                "status": item.status,
                "candidates": [
                    {
                        "instance_id": candidate.instance_id,
                        "profile_id": candidate.profile_id,
                        "installed": candidate.installed,
                        "configured": candidate.configured,
                    }
                    for candidate in item.candidates
                ],
            }
            for item in self.mapping.items
            if item.status == "needs_selection"
        ]
        return {
            "status": self.status,
            "can_apply": self.status == "ready",
            "content_id": self.content_id,
            "source_name": self.source_name,
            "apply_to_agents": self.apply_to_agents,
            "changed_file_count": self.changed_file_count,
            "conflicts": self.conflicts.public_data(),
            "agent_selections": agent_selections,
            "mapping_details": [{"logical_source": item.logical_source, "status": item.status, "detail": item.detail} for item in self.mapping.items],
        }


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _baseline_archive(package: CheckedPackage) -> bytes:
    manifest = json.dumps(_thaw(package.manifest), ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative, content in [("manifest.json", manifest), *sorted(package.payloads.items())]:
            member = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, content)
    return output.getvalue()


def _toml_setting(content: bytes | None, key: str, value: Any) -> bytes:
    import tomlkit

    try:
        document = tomlkit.parse(content.decode("utf-8") if content is not None else "")
    except (UnicodeDecodeError, ValueError) as error:
        raise PackageImportError("目标 Codex TOML 设置无法安全更新") from error
    document[key] = value
    return tomlkit.dumps(document).encode("utf-8")


def _json_setting(content: bytes | None, key: str, value: Any) -> bytes:
    try:
        document = json.loads(content.decode("utf-8-sig")) if content is not None else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackageImportError("目标 Claude JSON 设置无法安全更新") from error
    if not isinstance(document, dict):
        raise PackageImportError("目标 Claude 设置必须是 JSON 对象")
    document[key] = value
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _registry_toml(value: bytes) -> bytes:
    try:
        registry = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackageImportError("Agent 规则登记内容格式无效") from error
    if not isinstance(registry, dict):
        raise PackageImportError("Agent 规则登记内容必须是对象")
    lines: list[str] = []
    for profile, specification in sorted(registry.items()):
        if (
            not isinstance(profile, str)
            or profile not in agents.PROFILES
            or not agents.PROFILES[profile].writable
            or not isinstance(specification, dict)
            or set(specification) != {"topics"}
        ):
            raise PackageImportError("Agent 规则登记内容包含不支持字段")
        topics = specification["topics"]
        if not isinstance(topics, list) or any(not isinstance(topic, str) for topic in topics):
            raise PackageImportError("Agent 规则登记主题格式无效")
        lines.append(f"[{profile}]")
        lines.append("topics = [" + ", ".join(json.dumps(topic, ensure_ascii=False) for topic in topics) + "]")
        lines.append("")
    return ("\n".join(lines)).encode("utf-8")


def _replace_rules(current: bytes | None, block: bytes, mode: str) -> bytes:
    if mode == agents.MODE_FILE:
        if current is None:
            return block + b"\n"
        old, error = managed_block(current)
        if error is not None or old is None:
            raise PackageImportError("Agent 所有权文件不含可安全替换的受管区块")
        outside = current[:current.index(old)] + current[current.index(old) + len(old):]
        if outside.strip():
            raise PackageImportError("Agent 所有权文件含受管区块外内容，停止覆盖")
        return block + b"\n"
    if current is None:
        return block + b"\n"
    old, error = managed_block(current)
    if error == "no_managed_block":
        separator = b"\n" if not current or current.endswith((b"\n", b"\r")) else b"\n\n"
        return current + separator + block + b"\n"
    if error is not None or old is None:
        raise PackageImportError("Agent 规则受管区块损坏，停止替换")
    start = current.index(old)
    stop = start + len(old)
    return current[:start] + block + current[stop:]


def _plan_changes(
    package: CheckedPackage,
    mapping: PackageMappingPlan,
    conflicts: PackageConflictPlan,
    snapshot: PackageTargetSnapshot,
    *,
    device_config_path: Path,
    original_config_bytes: bytes,
    state_root: Path,
    baseline_path: Path,
    apply_to_agents: bool,
) -> PlannedChanges:
    changes: dict[Path, bytes | None] = {}
    expected: dict[Path, str | None] = dict(snapshot.observed_hashes)
    expected[device_config_path] = digest(original_config_bytes)
    baseline_original = _file_bytes(baseline_path, limit=MAX_ARCHIVE_BYTES)
    expected[baseline_path] = digest(baseline_original)
    rows = {row.key: row for row in conflicts.rows}
    incoming = {
        entry["logical_source"]: (entry, package.payloads[entry["object_path"]])
        for entry in package.manifest["entries"]
    }
    items_by_source: dict[str, list[Any]] = {}
    for item in mapping.items:
        items_by_source.setdefault(item.logical_source, []).append(item)

    setting_store_changes: dict[Path, list[tuple[str, Any]]] = {}
    for logical, (entry, _) in incoming.items():
        if entry["data_type"] == "agent_declaration" and logical.endswith("/declarations.json"):
            continue
        item = next((value for value in items_by_source.get(logical, ()) if value.storage_path is not None), None)
        if item is None:
            raise PackageImportError("包条目缺少已校验的配置库存储映射")
        value = conflicts.resolved_store_values.get(logical)
        if entry["data_type"] == "rule_file":
            original = _file_bytes(item.storage_path)
            if value is not None and original != value:
                expected.setdefault(item.storage_path, digest(original))
                changes[item.storage_path] = value
        elif entry["data_type"] == "shared_setting" and value is not None:
            setting_store_changes.setdefault(item.storage_path, []).append((logical, json.loads(value.decode("utf-8"))))
        elif logical == "agent://shared/agents-registry.json" and value is not None:
            current = _file_bytes(item.storage_path)
            desired = _registry_toml(value)
            if current != desired:
                expected.setdefault(item.storage_path, digest(current))
                changes[item.storage_path] = desired
        elif entry["data_type"] in {"skill_file", "mcp_config", "memory_snapshot", "handoff_record"} and value is not None:
            original = _file_bytes(item.storage_path)
            if original != value:
                expected.setdefault(item.storage_path, digest(original))
                changes[item.storage_path] = value
            live_row = rows.get(f"extension:{logical}")
            if apply_to_agents and item.target_path is not None and live_row and live_row.decision == "use_package":
                old = changes.get(item.target_path, _file_bytes(item.target_path))
                desired = value
                if entry["data_type"] == "mcp_config":
                    import tomlkit
                    document = tomlkit.parse((old or b"").decode("utf-8"))
                    from urllib.parse import unquote, urlsplit
                    name = unquote(urlsplit(logical).path.split("/")[1])
                    if "mcp_servers" not in document:
                        document["mcp_servers"] = tomlkit.table()
                    document["mcp_servers"][name] = json.loads(value)
                    desired = tomlkit.dumps(document).encode("utf-8")
                if old != desired:
                    expected.setdefault(item.target_path, digest(_file_bytes(item.target_path)))
                    changes[item.target_path] = desired

    for path, records in setting_store_changes.items():
        original = _file_bytes(path)
        current = original
        for logical, fragment in records:
            profile_id = logical.split("://", 1)[1].split("/", 1)[0]
            key = logical.rsplit("/", 1)[-1]
            if not isinstance(fragment, dict) or set(fragment) != {key}:
                raise PackageImportError("共享设置字段与逻辑来源不一致")
            value = fragment[key]
            if profile_id == "codex":
                current = _toml_setting(current, key, value)
            elif profile_id == "claude":
                current = _json_setting(current, key, value)
            else:
                raise PackageImportError("没有受支持的共享设置写入适配器")
        if current != original:
            expected.setdefault(path, digest(original))
            changes[path] = current

    resolved_config = deepcopy(dict(conflicts.proposed_device_config or {})) if apply_to_agents else None
    if apply_to_agents:
        for logical, (entry, _) in incoming.items():
            if entry["data_type"] != "shared_setting":
                continue
            row = rows.get(f"agent:{logical}")
            if row is None or row.decision != "use_package":
                continue
            item = next((value for value in items_by_source.get(logical, ()) if value.target_path is not None), None)
            if item is None:
                raise PackageImportError("Agent 设置缺少已校验的本机目标映射")
            fragment = conflicts.resolved_store_values.get(logical)
            if fragment is None:
                continue
            decoded = json.loads(fragment.decode("utf-8"))
            key = logical.rsplit("/", 1)[-1]
            current = _file_bytes(item.target_path)
            profile_id = item.profile_id
            if profile_id == "codex":
                desired = _toml_setting(current, key, decoded[key])
            elif profile_id == "claude":
                desired = _json_setting(current, key, decoded[key])
            else:
                raise PackageImportError("没有受支持的 Agent 设置写入适配器")
            if current != desired:
                expected.setdefault(item.target_path, digest(current))
                changes[item.target_path] = desired

        if resolved_config and resolved_config != json.loads(original_config_bytes.decode("utf-8-sig")):
            # The conflict planner's receiver copy is the only source of paths and
            # identities. Validate it again before persisting local device state.
            validate_device_config(resolved_config)
            encoded_config = (json.dumps(resolved_config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if encoded_config != original_config_bytes:
                changes[device_config_path] = encoded_config

        desired_rule_files = dict(snapshot.rule_files)
        from ..config import SHARED_RULE_TOPICS
        for topic in SHARED_RULE_TOPICS:
            logical = f"agent://shared/common/{topic}.md"
            if logical in conflicts.resolved_store_values:
                desired_rule_files[topic] = conflicts.resolved_store_values[logical]
        for target in snapshot.agent_rules:
            row = rows.get(f"agent-rules:{target.instance_id}")
            if row is None or row.decision != "use_package":
                continue
            target_instance = SimpleNamespace(id=target.instance_id, topics=target.topics)
            block = _render_rules_block(desired_rule_files, target_instance, resolved_config or {})
            current = _file_bytes(target.path)
            desired = _replace_rules(current, block, target.mode)
            if current != desired:
                expected.setdefault(target.path, digest(current))
                changes[target.path] = desired

    # Retain the exact checked package as the next offline common baseline. It
    # is journaled and backed up with the same transaction as user-visible data.
    baseline_bytes = _baseline_archive(package)
    if len(baseline_bytes) > MAX_ARCHIVE_BYTES:
        raise PackageImportError("本机父版本包超过归档大小上限")
    if baseline_bytes != baseline_original:
        changes[baseline_path] = baseline_bytes

    return PlannedChanges(
        changes,
        expected=expected,
        state_root=state_root,
        metadata={
            "operation": "migrate",
            "package_content_id": package.validation["content_id"],
            "path_agents": {
                str(item.target_path): item.profile_id
                for item in mapping.items
                if item.target_path is not None and item.profile_id is not None
            },
        },
    )


class PackageImportService:
    """Prepare, revalidate, atomically journal and undo package imports."""

    def __init__(self, device_config_path: Path, *, host: agents.HostEnv | None = None) -> None:
        self.device_config_path = Path(device_config_path).expanduser().absolute()
        self.host = host
        self._plans: dict[str, PackageImportPlan] = {}

    def preview(
        self,
        package_path: Path,
        *,
        store_root: Path | None = None,
        decisions: Mapping[str, str] | None = None,
        manual_values: Mapping[str, bytes] | None = None,
        apply_to_agents: bool = True,
        selections: Mapping[str, str] | None = None,
    ) -> PackageImportPlan:
        from ..config import absolute
        from ..config_source import source_root

        source = Path(package_path).expanduser().absolute()
        try:
            package = check_package(source, supported_adapters=SUPPORTED_ADAPTERS)
            original_config_bytes = _file_bytes(self.device_config_path)
            if original_config_bytes is None:
                raise PackageImportError("接收设备配置文件不存在")
            raw_config = json.loads(original_config_bytes.decode("utf-8-sig"))
            if not isinstance(raw_config, dict):
                raise ValueError("Device configuration must be an object")
            validate_device_config(raw_config)
        except (PackageCheckError, OSError, ValueError) as error:
            raise PackageImportError("迁移包或接收设备配置无法安全检查") from error
        if not raw_config.get("config_repo"):
            raise PackageImportError("本机没有登记配置库路径；请先完成首次设置")
        store = Path(store_root).expanduser().absolute() if store_root is not None else Path(source_root(raw_config)).absolute()
        state_root = absolute(raw_config["state_dir"])
        baseline_path = state_root / "package-baseline.aiconfig"
        base_package = None
        parent = package.manifest.get("parent_content_id")
        if parent and baseline_path.is_file():
            try:
                candidate = check_package(baseline_path, supported_adapters=SUPPORTED_ADAPTERS)
                if candidate.validation.get("content_id") == parent:
                    base_package = candidate
            except PackageCheckError:
                base_package = None

        try:
            mapping = plan_package_mappings(
                package,
                store_root=store,
                device_config=raw_config,
                host=self.host,
                selections=selections,
            )
            targets = inspect_package_targets(package, mapping, store_root=store)
            conflicts = plan_package_conflicts(
                package,
                mapping,
                targets,
                decisions=decisions,
                base_package=base_package,
                manual_values=manual_values,
            )
        except (PackageMappingError, PackageConflictError, OSError, ValueError) as error:
            raise PackageImportError("接收端映射或冲突预览无法安全完成") from error

        can_apply = conflicts.can_update_store and (not apply_to_agents or conflicts.can_apply_to_agents)
        if not can_apply:
            changes = PlannedChanges(state_root=state_root)
            status = conflicts.status if conflicts.status != "ready" else "needs_resolution"
        else:
            try:
                changes = _plan_changes(
                    package,
                    mapping,
                    conflicts,
                    targets,
                    device_config_path=self.device_config_path,
                    original_config_bytes=original_config_bytes,
                    state_root=state_root,
                    baseline_path=baseline_path,
                    apply_to_agents=apply_to_agents,
                )
            except (OSError, PackageConflictError, PackageImportError, ValueError, TypeError) as error:
                raise PackageImportError("无法生成安全的导入事务；目标未修改") from error
            status = "ready" if changes else "unchanged"

        plan_id = uuid.uuid4().hex
        plan = PackageImportPlan(
            plan_id,
            status,
            package.validation["content_id"],
            source.name,
            apply_to_agents,
            len(changes),
            conflicts,
            mapping,
            targets,
            changes,
            source,
            baseline_path,
            state_root / "backups",
            state_root,
            package.manifest["package_id"],
        )
        self._plans[plan.plan_id] = plan
        # A small cap prevents abandoned UI previews retaining package bytes forever.
        while len(self._plans) > 8:
            self._plans.pop(next(iter(self._plans)))
        return plan

    def apply(self, plan_id: str) -> dict[str, Any]:
        plan = self._plans.pop(plan_id, None)
        if plan is None:
            raise PackageImportError("导入预览已过期；请重新检查迁移包")
        if plan.status == "unchanged":
            return {"status": "unchanged", "content_id": plan.content_id, "operation_id": None, "changed_file_count": 0}
        if plan.status != "ready" or not plan.changes:
            raise PackageImportError("导入预览仍有未解决项目；没有写入任何文件")
        try:
            current = check_package(plan.package_path, supported_adapters=SUPPORTED_ADAPTERS)
        except (PackageCheckError, OSError) as error:
            raise PackageImportError("迁移包在预览后已不可读取；请重新检查") from error
        if (
            current.validation.get("content_id") != plan.content_id
            or current.manifest.get("package_id") != plan.expected_package_id
        ):
            raise PackageImportError("迁移包在预览后发生变化；请重新检查")

        baseline_path = plan.baseline_path
        try:
            for path, expected_hash in plan.changes.expected.items():
                limit = MAX_ARCHIVE_BYTES if path == baseline_path else MAX_TARGET_BYTES
                if digest(_file_bytes(path, limit=limit)) != expected_hash:
                    raise PackageImportError("目标文件在预览后发生变化；请重新生成导入预览")
        except PackageConflictError as error:
            raise PackageImportError("目标路径在预览后变得不安全；没有写入文件") from error

        def verified_writer(path: Path, data: bytes | None) -> None:
            write_file(path, data)
            actual = read_bytes(path)
            if actual != data:
                raise PackageImportError("目标回读内容与导入计划不一致")
            if path == baseline_path and data is not None:
                verified = check_package(path, supported_adapters=SUPPORTED_ADAPTERS)
                if verified.validation.get("content_id") != plan.content_id:
                    raise PackageImportError("保存的本机父版本未通过内容核验")

        try:
            backup = transaction(
                plan.changes,
                plan.backup_root,
                state_root=plan.state_root,
                operation_id=plan.plan_id,
                writer=verified_writer,
            )
        except SyncBusyError as error:
            raise PackageImportError("另一个本机同步事务正在运行；请稍后重新预览") from error
        except Exception as error:
            raise PackageImportError("导入事务未完成；已有文件已自动恢复或需在历史恢复页处理") from error
        return {
            "status": "applied",
            "content_id": plan.content_id,
            "operation_id": plan.plan_id,
            "backup_created": backup is not None,
            "changed_file_count": len(plan.changes),
            "note": "目标文件已逐项回读核验；本机父版本已保存，可在操作历史中撤销。",
        }
