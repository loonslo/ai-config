"""Application operations shared by the CLI and future desktop client.

The service returns structured data and keeps terminal rendering in
``scripts/sync.py``. Construction and import are side-effect free; each method
performs filesystem work only when explicitly called.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from ..transaction import PlannedChanges


def _shared_value_for(
    tool: str, key: str, config: Mapping[str, Any], *, default_root: Path | None = None
) -> Any:
    """Read one managed value from the configured portable source."""
    import json

    from ..planning import source_root

    root = source_root(config, default_root=default_root)
    try:
        if tool == "codex":
            import tomlkit

            document = tomlkit.parse((root / "codex/config.toml").read_text(encoding="utf-8"))
            return str(document[key]) if key in document else None
        if tool == "claude":
            document = json.loads((root / "claude/settings.shared.json").read_text(encoding="utf-8"))
            return document.get(key)
    except (OSError, ValueError, KeyError):
        return None
    return None


def _observed_values(tool: str, config: Mapping[str, Any]) -> dict[str, Any]:
    """Read the managed settings currently present in one local agent file."""
    import json

    from ..config import absolute

    root = config.get(tool)
    if not root:
        return {}
    try:
        if tool == "codex":
            import tomlkit

            path = absolute(root) / "config.toml"
            if not path.exists():
                return {}
            document = tomlkit.parse(path.read_text(encoding="utf-8"))
            return {key: str(document[key]) for key in config.get("codex_keys", []) if key in document}
        path = absolute(root) / "settings.json"
        if not path.exists():
            return {}
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(document, dict):
            return {}
        return {key: document[key] for key in config.get("claude_keys", []) if key in document}
    except (OSError, ValueError):
        return {}


def generated_device_config() -> dict[str, Any]:
    """Build the same conservative default used by the quick setup entry."""
    import platform
    import re

    from ..config import selected_claude_keys, selected_codex_keys

    system = platform.system().casefold()
    prefix = "mac" if system == "darwin" else "windows" if system == "windows" else system or "device"
    node = re.sub(r"[^a-z0-9_-]+", "-", platform.node().casefold()).strip("-") or "local"
    home = Path.home()
    config: dict[str, Any] = {
        "device": f"{prefix}-{node}"[:48].rstrip("-"),
        "state_dir": str(home / ".ai-sync" / "state"),
        "memory_repo": str(home / "ai-memory"),
        "codex": str(home / ".codex"),
        "claude": str(home / ".claude"),
        "codex_keys": [],
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "tool_versions": {},
        "additional_sources": [],
        "codex_memory": str(home / ".codex" / "memories"),
        "memories": [],
        "projects": {},
    }
    config["codex_keys"] = list(selected_codex_keys(config))
    config["claude_keys"] = list(selected_claude_keys(config))
    return config


@dataclass(frozen=True)
class ApplicationResult:
    """A client-facing result plus optional in-process detail for CLI rendering."""

    data: dict[str, Any]
    detail: Any = None


def plan_local_changes(
    config: dict[str, Any], mode: str, *, template_root: Path | None = None
) -> PlannedChanges:
    """Build the same no-write plan used by a CLI or desktop preview."""
    from .. import planning
    from ..config import absolute

    state = absolute(config["state_dir"])
    if mode == "rules":
        return planning.rules_plan(config, state, default_root=template_root)
    if mode == "config":
        return planning.config_plan(config, state, default_root=template_root)
    if mode == "memory":
        return planning.memory_plan(config, state, default_root=template_root)
    raise ValueError(f"Unsupported sync mode: {mode}")


class ApplicationService:
    """Operations for one local device configuration path."""

    def __init__(self, local_path: Path, *, template_root: Path | None = None) -> None:
        self.local_path = Path(local_path)
        self.template_root = Path(template_root) if template_root is not None else None

    def _raw_config(self) -> dict[str, Any]:
        from ..config import load

        if not self.local_path.is_file():
            raise FileNotFoundError(f"Device configuration not found: {self.local_path}")
        return load(self.local_path).raw

    def import_config(self, *, source: Path, apply: bool = False) -> ApplicationResult:
        """Preview or copy an existing device configuration into the user data area."""
        from ..layout import import_device_config, plan_device_config_import

        plan = plan_device_config_import(Path(source), self.local_path)
        if apply:
            report = import_device_config(plan)
            return ApplicationResult(data=report, detail=plan)
        return ApplicationResult(
            data={
                "status": "preview",
                "source": str(plan.source),
                "target": str(plan.target),
                "backup": str(plan.backup) if plan.action == "copy" else None,
                "written": False,
            },
            detail=plan,
        )

    def package_import(
        self,
        *,
        package_path: Path,
        decisions: Mapping[str, str] | None = None,
        manual_values: Mapping[str, str] | None = None,
        selections: Mapping[str, str] | None = None,
        apply_to_agents: bool = True,
        apply: bool = False,
    ) -> ApplicationResult:
        """Preview or commit a checked offline package through a local transaction."""
        from ..package.importer import PackageImportService

        importer = PackageImportService(self.local_path)
        plan = importer.preview(
            Path(package_path),
            decisions=decisions,
            manual_values={key: value.encode("utf-8") for key, value in (manual_values or {}).items()},
            selections=selections,
            apply_to_agents=apply_to_agents,
        )
        if not apply:
            return ApplicationResult(data=plan.public_data(), detail=plan.changes)
        if plan.status != "ready":
            raise ValueError("迁移包仍有未解决项目；没有写入任何文件。")
        result = importer.apply(plan.plan_id)
        return ApplicationResult(data=result, detail=plan.changes)

    def package_export(
        self,
        *,
        destination: Path,
        format: str,
        selected_sources: list[str] | None = None,
        extension_kinds: list[str] | None = None,
        apply: bool = False,
    ) -> ApplicationResult:
        """Preview a fixed allowlist export and publish it only after confirmation."""
        from ..config_source import source_root
        from ..package.export import (
            PackageExportError,
            build_package_manifest,
            collect_portable_config,
            export_archive,
            export_directory,
            select_portable_sources,
        )

        if format not in {"archive", "directory"}:
            raise ValueError("迁移包格式必须是 archive 或 directory。")
        raw = self._raw_config()
        if not raw.get("config_repo"):
            raise ValueError("本机没有登记配置库路径；请先完成首次设置。")
        root = Path(source_root(raw))
        target = Path(destination).expanduser().absolute()
        collected = collect_portable_config(raw, root, extension_kinds=extension_kinds)
        selected = (
            sorted(entry.logical_source for entry in collected.entries)
            if selected_sources is None
            else selected_sources
        )
        report = select_portable_sources(collected, selected)
        summary = report.public_summary()
        can_apply = bool(report.entries) and not report.review_required and not report.unsupported
        content_id = None
        error = None
        if can_apply:
            try:
                manifest, _objects = build_package_manifest(report)
                content_id = manifest["content_id"]
            except PackageExportError as exc:
                can_apply = False
                error = str(exc)
        if target.exists() or target.is_symlink():
            can_apply = False
            error = "目标位置已存在；请另选一个新文件名或目录名。"
        elif not target.parent.is_dir():
            can_apply = False
            error = "目标父目录不存在；请先选择现有目录。"
        if format == "archive" and target.suffix.casefold() != ".aiconfig":
            can_apply = False
            error = "归档文件名必须以 .aiconfig 结尾。"
        data = {
            "status": "ready" if can_apply else "review_required" if report.review_required or report.unsupported else "blocked",
            "can_apply": can_apply,
            "format": format,
            "destination_name": target.name,
            "content_id": content_id,
            "selected_sources": selected,
            "scope_items": [
                {
                    "logical_source": item.logical_source,
                    "data_type": item.data_type,
                    "status": "ready",
                    "selected": item.logical_source in selected,
                    "selectable": True,
                }
                for item in collected.entries
            ] + [
                {
                    "logical_source": issue.logical_source,
                    "data_type": issue.category,
                    "status": "review_required",
                    "detail": issue.detail,
                    "selected": issue.logical_source in selected,
                    "selectable": True,
                }
                for issue in collected.review_required
            ] + [
                {
                    "logical_source": issue.logical_source,
                    "data_type": issue.category,
                    "status": "unsupported",
                    "detail": issue.detail,
                    "selected": issue.logical_source in selected,
                    "selectable": True,
                }
                for issue in collected.unsupported
            ] + [
                {
                    "logical_source": issue.logical_source,
                    "data_type": issue.category,
                    "status": "excluded",
                    "detail": issue.detail,
                    "selected": False,
                    "selectable": False,
                }
                for issue in collected.exclusions
            ],
            "entry_count": len(report.entries),
            "exclusion_count": len(report.exclusions),
            "exclusions": summary["excluded"],
            "review_required": summary["review_required"],
            "unsupported": summary["unsupported"],
            "unclassified_top_level_count": report.unclassified_top_level_count,
            "reason": error,
        }
        if not apply:
            return ApplicationResult(data=data, detail={"report": report, "target": target, "format": format})
        if not can_apply:
            raise ValueError("迁移包范围尚未解决或目标不可用；没有生成文件。")
        if format == "archive":
            exported = export_archive(report, target, config=raw, store_root=root, selected_sources=selected)
        else:
            exported = export_directory(report, target, config=raw, store_root=root, selected_sources=selected)
        return ApplicationResult(data={
            "status": "exported",
            "written": True,
            "format": exported.format,
            "destination_name": target.name,
            "content_id": exported.content_id,
            "entry_count": exported.entry_count,
            "object_count": exported.object_count,
        }, detail={"report": report, "target": target, "format": format})

    def extension_capture(self, *, kind: str, profile: str, name: str, source: Path, apply: bool = False) -> ApplicationResult:
        from ..config_source import source_root
        from ..package.extensions import capture
        config = self._raw_config()
        result, plan = capture(config, Path(source_root(config)), kind=kind, profile=profile, name=name, source=source, apply=apply)
        return ApplicationResult(data=result, detail=plan)

    def package_capabilities(self) -> ApplicationResult:
        from ..package.extensions import capabilities
        return ApplicationResult(data={"capabilities": capabilities()})

    def portable_project(self, *, project_id: str, profile: str, handoff_id: str | None = None) -> ApplicationResult:
        from ..config_source import source_root
        from ..package.extensions import portable_project_report
        raw = self._raw_config()
        return ApplicationResult(data=portable_project_report(raw, Path(source_root(raw)), project_id=project_id,
                                                             profile=profile, handoff_id=handoff_id))

    def portable_restore(self, *, project_id: str, profile: str, apply: bool = False) -> ApplicationResult:
        from ..config import absolute
        from ..config_source import source_root
        from ..package.extensions import collect_extensions
        from ..package.policy import CollectionReport
        from ..package.conflicts import _file_bytes
        from ..transaction import transaction
        from ..utils import digest
        import re
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", project_id) or profile != "claude":
            raise ValueError("仅可恢复映射的 Claude Markdown；Codex 保持参考资料。")
        raw = self._raw_config()
        mapping = next((item for item in raw.get("memories", []) if item.get("id") == project_id), None)
        if mapping is None:
            raise ValueError("请先为该项目选择本机记忆目录。")
        report = collect_extensions(Path(source_root(raw)), CollectionReport((), (), (), (), 0), ["memory"])
        prefix = f"memory://claude/{project_id}/"
        selected = [entry for entry in report.entries if entry.logical_source.startswith(prefix)]
        if not selected or report.unsupported:
            raise ValueError("没有已校验的对应可移植快照。")
        from urllib.parse import unquote
        target_root = absolute(mapping["path"])
        changes, expected = {}, {}
        for entry in selected:
            relative = unquote(entry.logical_source[len(prefix):])
            target = target_root / relative
            old = _file_bytes(target)
            expected[target] = digest(old)
            if old != entry.content:
                changes[target] = entry.content
        plan = PlannedChanges(changes, expected=expected, state_root=absolute(raw["state_dir"]), metadata={"operation": "migrate"})
        result = {"status": "ready", "can_apply": bool(plan), "project_id": project_id, "file_count": len(changes),
                  "paths": [str(path) for path in changes], "note": "确认将备份并恢复所列 Markdown；源码与 Agent 新会话仍需核验。"}
        if apply and plan:
            transaction(plan, absolute(raw["state_dir"]) / "backups", state_root=absolute(raw["state_dir"]))
            result.update(status="restored", written=True)
        return ApplicationResult(data=result, detail=plan)

    def git_transport(self, *, action: str, apply: bool = False) -> ApplicationResult:
        from .. import config_source
        import shutil
        if action not in {"fetch", "publish"}:
            raise ValueError("Git 传输只允许获取或发布。")
        raw = self._raw_config()
        ready = shutil.which("git") is not None and (Path(config_source.source_root(raw)) / ".git").exists()
        if not apply:
            from ..package.policy import collect_portable_config
            source_facts = collect_portable_config(raw, Path(config_source.source_root(raw)))
            return ApplicationResult(data={"status": "ready" if ready else "blocked", "can_apply": ready,
                                           "action": action, "note": "只预览本次传输意图；获取后请重新预览本机应用，传输成功不等于 Agent 已应用。"},
                                     detail={"sources": source_facts, "head": config_source.head(Path(config_source.source_root(raw))) if ready else None})
        if not ready:
            raise ValueError("当前配置库未使用 Git 或 Git 不可用；离线迁移不受影响。")
        report = config_source.fetch(raw) if action == "fetch" else config_source.publish(raw, apply=True)
        return ApplicationResult(data=report)

    def cloud(self, *, server: str, action: str, options: Mapping[str, Any] | None = None, apply: bool = False) -> ApplicationResult:
        import hashlib
        from ..cloud.client import CloudClient, secure_url, read_upload_package
        server = secure_url(server)
        options = dict(options or {})
        detail: dict[str, Any] = {}
        if action == "upload":
            path = Path(options["package_path"])
            if not path.is_absolute() or not path.is_file():
                raise ValueError("请先选择已导出的单文件包。")
            checked, plaintext = read_upload_package(path)
            detail = {"path": path, "content_id": checked.validation["content_id"], "sha256": hashlib.sha256(plaintext).hexdigest()}
        if action == "download":
            path = Path(options["destination"])
            if not path.is_absolute() or path.exists() or not path.parent.is_dir():
                raise ValueError("请选择新的下载文件名。")
            detail = {"destination": path}
        if not apply:
            return ApplicationResult(data={"can_apply": True, "action": action, "server": server, "status": "ready",
                                           "note": "确认后执行所选云端操作；离线配置与 Agent 文件不会自动应用。"}, detail=detail)
        raw = self._raw_config()
        state = Path(raw["state_dir"]) if raw.get("state_dir") else self.local_path.parent / "state"
        client = CloudClient(server, state)
        try:
            result = client.execute(action, options)
        except ValueError:
            raise
        except Exception as error:
            raise ValueError("云端或安全存储操作未完成；请核对网络、身份与配置。原本机数据保留。") from error
        finally:
            client.close()
        return ApplicationResult(data=result)

    def plan(self, *, mode: str) -> PlannedChanges:
        """Build a local rules, configuration, or memory change plan."""
        return plan_local_changes(self._raw_config(), mode, template_root=self.template_root)

    def rule_library(self) -> ApplicationResult:
        """Read editable shared rule files without returning suspected credentials."""
        from ..config import SHARED_RULE_TOPICS
        from ..planning import source_root
        from ..utils import SECRET

        raw = self._raw_config()
        if not raw.get("config_repo"):
            raise ValueError("本机没有登记可编辑的规则配置库；请先完成首次设置。")
        root = source_root(raw)
        common = root / "common"
        rows: list[dict[str, Any]] = []
        paths: list[Path] = []
        unsafe_tree = root.is_symlink() or common.is_symlink()
        for topic in SHARED_RULE_TOPICS:
            path = common / f"{topic}.md"
            paths.append(path)
            if unsafe_tree or path.is_symlink():
                rows.append({"topic": topic, "status": "blocked_symlink", "content": ""})
                continue
            try:
                data = path.read_bytes() if path.is_file() else b""
                text = data.decode("utf-8-sig")
            except (OSError, UnicodeDecodeError):
                rows.append({"topic": topic, "status": "unreadable", "content": ""})
                continue
            if len(data) > 262144:
                rows.append({"topic": topic, "status": "too_large", "content": ""})
            elif SECRET.search(text):
                rows.append({"topic": topic, "status": "blocked_secret", "content": ""})
            else:
                rows.append({"topic": topic, "status": "ready", "content": text})
        return ApplicationResult(
            data={"rules": rows, "store_path": str(root)},
            detail={"paths": paths},
        )

    def save_rule(self, *, topic: str, content: str, apply: bool = False) -> ApplicationResult:
        """Preview or save one shared rule file to the local configuration store."""
        from ..config import SHARED_RULE_TOPICS, absolute
        from ..planning import read, source_root
        from ..transaction import PlannedChanges, transaction
        from ..utils import SECRET, digest

        if topic not in SHARED_RULE_TOPICS:
            raise ValueError("不支持的共享规则主题。")
        if not isinstance(content, str) or "\x00" in content:
            raise ValueError("规则内容必须是 UTF-8 文本。")
        encoded = content.encode("utf-8")
        if len(encoded) > 262144:
            raise ValueError("单个规则文件不能超过 256 KiB。")
        if SECRET.search(content):
            raise ValueError("疑似包含凭据；内容未保存，请删除凭据或改用本机安全存储。")

        raw = self._raw_config()
        if not raw.get("config_repo"):
            raise ValueError("本机没有登记可编辑的规则配置库；请先完成首次设置。")
        root = source_root(raw)
        common = root / "common"
        target = common / f"{topic}.md"
        if root.is_symlink() or common.is_symlink() or not common.is_dir() or target.is_symlink():
            raise ValueError("规则配置库目录缺失或包含符号链接；未保存内容。")
        current = read(target)
        if current == encoded:
            return ApplicationResult(data={"status": "unchanged", "topic": topic, "ready": False, "written": False})

        state = absolute(raw["state_dir"])
        plan = PlannedChanges(
            {target: encoded},
            expected={target: digest(current)},
            state_root=state,
            metadata={"operation": "save_rule", "path_agents": {}},
        )
        if not apply:
            return ApplicationResult(
                data={"status": "preview", "topic": topic, "target": f"common/{topic}.md", "bytes": len(encoded), "ready": True, "written": False},
                detail=plan,
            )
        backup = transaction(plan, state / "backups", state_root=state)
        return ApplicationResult(
            data={"status": "saved", "topic": topic, "target": f"common/{topic}.md", "bytes": len(encoded), "backup": str(backup) if backup else None, "ready": False, "written": True},
            detail=plan,
        )

    def apply_plan(self, plan: PlannedChanges, *, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Commit a plan with a backup, then persist operation-specific receipts."""
        from ..config_sync import record_created_dirs
        from ..memory_io import stable_files
        from ..snapshots import create_snapshot
        from ..transaction import SyncLock, transaction
        from ..config import absolute
        import json

        if plan.state_root is None:
            raise ValueError("Cannot apply a plan without its state root")
        state = plan.state_root
        if plan:
            transaction(plan, state / "backups", state_root=state)
        operation = plan.metadata.get("operation")
        if plan and operation == "rules":
            record_created_dirs(state, plan.metadata.get("created_dirs"))
        snapshots: list[str] = []
        effective_config = config
        if plan and operation == "memory" and effective_config is None:
            effective_config = self._raw_config()
        if plan and operation == "memory" and effective_config is not None:
            memory_root = absolute(effective_config["memory_repo"])
            memory_root.mkdir(parents=True, exist_ok=True)
            with SyncLock(state):
                for item in effective_config.get("memories", []):
                    source = absolute(item["path"])
                    if not source.is_dir():
                        raise ValueError(f"Memory source missing; cannot publish snapshot: {source}")
                    scope = item["id"]
                    head = memory_root / "heads" / effective_config["device"] / f"{scope}.json"
                    parent = json.loads(head.read_text(encoding="utf-8")).get("snapshot_id") if head.exists() else None
                    manifest = create_snapshot(
                        memory_root,
                        device=effective_config["device"],
                        scope=scope,
                        project_id=scope,
                        files=stable_files(source, item.get("exclude", [])),
                        parent_snapshot=parent,
                        source_id=f"claude:{scope}",
                    )
                    snapshots.append(manifest["snapshot_id"])
                if effective_config.get("codex_memory"):
                    source = absolute(effective_config["codex_memory"])
                    if not source.is_dir():
                        raise ValueError(f"Codex memory source missing; cannot publish snapshot: {source}")
                    scope = f"codex-{effective_config['device']}"
                    head = memory_root / "heads" / effective_config["device"] / f"{scope}.json"
                    parent = json.loads(head.read_text(encoding="utf-8")).get("snapshot_id") if head.exists() else None
                    manifest = create_snapshot(
                        memory_root,
                        device=effective_config["device"],
                        scope=scope,
                        tool="codex",
                        files=stable_files(source),
                        parent_snapshot=parent,
                        source_id="codex-memory",
                    )
                    snapshots.append(manifest["snapshot_id"])
        return {"status": "applied" if plan else "no_changes", "changes": len(plan), "snapshots": snapshots}

    def quick_setup(
        self,
        config: Mapping[str, Any] | None = None,
        *,
        generated: bool | None = None,
        apply: bool = False,
    ) -> ApplicationResult:
        """Plan or perform the existing local quick-setup flow."""
        from .. import inventory as inventory_core
        from ..config import DeviceConfig, load
        from ..inventory import persist_report
        from ..transaction import SyncLock
        from ..utils import atomic_write, json_bytes

        created_config = not self.local_path.is_file() if generated is None else generated
        if created_config and self.local_path.exists():
            raise FileExistsError(f"Quick setup will not replace an existing device configuration: {self.local_path}")
        raw_config = dict(config) if config is not None else generated_device_config()
        device = load(self.local_path) if self.local_path.is_file() else DeviceConfig(raw_config, self.local_path)
        raw = device.raw
        inventory = inventory_core.discover(device)
        rules = plan_local_changes(raw, "rules", template_root=self.template_root)
        settings = plan_local_changes(raw, "config", template_root=self.template_root)
        report: dict[str, Any] = {
            "status": "preview",
            "ready": False,
            "config_path": str(self.local_path.resolve()),
            "config_created": created_config,
            "device": raw["device"],
            "inventory_id": inventory["inventory_id"],
            "inventory_summary": inventory["summary"],
            "rules_changes": len(rules),
            "config_changes": len(settings),
            "memory_status": "not_run",
            "memory_note": "Memory sync requires an explicitly configured private ai-memory repository and mappings.",
        }
        if not apply:
            return ApplicationResult(data=report, detail={"inventory": inventory, "rules": rules, "config": settings})
        if created_config:
            atomic_write(self.local_path.resolve(), json_bytes(dict(raw)))
        if rules:
            self.apply_plan(rules, config=raw)
        if settings:
            self.apply_plan(settings, config=raw)
        with SyncLock(device.state_dir):
            inventory_path = persist_report(load(self.local_path), inventory)
        report.update({"status": "ready", "ready": True, "inventory_path": str(inventory_path)})
        return ApplicationResult(data=report, detail={"inventory": inventory, "rules": rules, "config": settings})

    def setup(
        self,
        *,
        store_path: Path | None = None,
        remote: str | None = None,
        state_dir: Path | None = None,
        memory_repo: Path | None = None,
        tools: list[str] | None = None,
        tool_roots: Mapping[str, str] | None = None,
        apply: bool = False,
    ) -> ApplicationResult:
        """Detect this computer and preview or write its local configuration."""
        from ..agents import HostEnv
        from ..config import absolute
        from ..environment import detect
        from ..layout import default_state_path
        from ..store import execute, plan_store
        from ..wizard import SetupCancelled, SetupError, plan_device, write_config

        home = Path.home()
        detected = detect(configured={}, home=home, host=HostEnv.current(), require_git=bool(remote))
        store_plan = plan_store(absolute(store_path), remote=remote) if store_path else None
        installed = [item["tool"] for item in detected["tools"] if item["installed"]]
        selected_tools = sorted(set(tools if tools is not None else installed))
        overrides = dict(tool_roots or {})
        unknown_overrides = set(overrides) - set(selected_tools)
        if unknown_overrides:
            raise ValueError("只能为已选择的 Agent 设置目录：" + ", ".join(sorted(unknown_overrides)))
        roots = {
            item["tool"]: str(overrides.get(item["tool"], item["root"]))
            for item in detected["tools"]
            if item["tool"] in selected_tools and item.get("root")
        }
        for tool, root in overrides.items():
            candidate = Path(root).expanduser()
            if not candidate.is_absolute():
                raise ValueError(f"{tool} 的配置目录必须是绝对路径。")
            roots[tool] = str(candidate)
        ready = bool(detected.get("ready")) and bool(selected_tools)
        report: dict[str, Any] = {
            "status": "preview",
            "ready": ready,
            "detected": detected,
            "tools": selected_tools,
            "store": store_plan,
            "written": False,
        }
        if not apply:
            if ready:
                try:
                    config = plan_device(
                        state_dir=absolute(state_dir or default_state_path()),
                        memory_repo=absolute(memory_repo or home / "ai-memory"),
                        tools=selected_tools,
                        scope="rules_only",
                        remote_url=remote,
                        tool_roots=roots,
                    )
                    report["config"] = config
                except (SetupError, SetupCancelled) as error:
                    report.update({"ready": False, "reason": str(error)})
            return ApplicationResult(data=report, detail={"config": report.get("config")})

        if not ready:
            report.update({"status": "blocked", "reason": "环境未就绪，或没有选择已安装的 agent。"})
            return ApplicationResult(data=report)
        try:
            config = plan_device(
                state_dir=absolute(state_dir or default_state_path()),
                memory_repo=absolute(memory_repo or home / "ai-memory"),
                tools=selected_tools,
                scope="rules_only",
                remote_url=remote,
                tool_roots=roots,
            )
        except (SetupError, SetupCancelled) as error:
            report.update({"status": "blocked", "ready": False, "reason": str(error)})
            return ApplicationResult(data=report)
        if store_plan:
            config["config_repo"] = str(execute(store_plan))
        written = write_config(config, self.local_path)
        report.update({
            "status": "configured",
            "ready": True,
            "config": config,
            "config_path": written["config_path"],
            "backup": written["backup"],
            "written": True,
            "note": "本机配置已写入；这不代表其他设备已经同步。",
        })
        return ApplicationResult(data=report, detail={"config": config})

    def sync(
        self,
        *,
        apply: bool = False,
        fetch: bool = False,
        publish: bool = False,
        checkpoint: Callable[[str], None] | None = None,
    ) -> ApplicationResult:
        """Run configuration reconciliation with separately reported transport stages."""
        from .. import config_source, receipts
        from ..config import DeviceConfig
        from ..config_sync import ConfigSyncError, state_for, sync as reconcile

        config = self._raw_config()
        device = DeviceConfig(config, self.local_path)

        def do_fetch() -> dict[str, Any]:
            if not fetch:
                return {"status": "skipped", "detail": "未请求下载：只使用本机已有的配置源副本。"}
            report = config_source.fetch(config)
            if report.get("status") in {"diverged", "blocked"}:
                raise ConfigSyncError("fetch", str(report.get("detail") or "配置源与远端不一致。"), exit_code=4)
            return report

        def do_publish(should_apply: bool) -> dict[str, Any]:
            if not publish:
                return {"status": "skipped", "detail": "未请求发布：共享修改只保存在本机。"}
            return config_source.publish(config, apply=should_apply)

        def do_receipt() -> dict[str, Any]:
            if not config.get("remote_identity"):
                return {"status": "not_configured", "detail": "本机配置未记录配置源地址，跳过状态上报。"}
            try:
                return receipts.publish_receipt(config_source.source_root(config), state_for(device))
            except receipts.ReceiptUnavailable as error:
                return {"status": "not_configured", "detail": str(error)}

        report = reconcile(
            device,
            apply=apply,
            fetch=do_fetch,
            publish=do_publish,
            receipt=do_receipt,
            checkpoint=checkpoint or (lambda _stage: None),
        )
        return ApplicationResult(data=report, detail=report)

    def status(self) -> ApplicationResult:
        """Return the local configuration state and any safely readable receipts."""
        from .. import agents, config_source, messages
        from ..config import DeviceConfig
        from ..config_sync import state_for
        from ..receipts import fetch_receipts

        if not self.local_path.exists():
            return ApplicationResult(
                data={
                    "status": "not_configured",
                    "configured": False,
                    "state": None,
                    "receipts": [],
                    "next_step": "首次设置",
                },
            )
        config = self._raw_config()
        state = state_for(DeviceConfig(config, self.local_path))
        try:
            receipt_rows = fetch_receipts(config_source.source_root(config))
        except Exception:  # noqa: BLE001 - offline status must remain available
            receipt_rows = []
        next_step = messages.next_step_for_status(state["capabilities"]["config"]["status"])
        registered_agents = [
            {"id": instance.id, "name": agents.display_name(instance.id)}
            for instance in agents.agent_instances(config)
        ]
        return ApplicationResult(
            data={"state": state, "receipts": receipt_rows, "agents": registered_agents, "next_step": next_step},
            detail={"state": state, "receipts": receipt_rows, "agents": registered_agents},
        )

    def diff(self, *, choice: str | None = None, apply: bool = False) -> ApplicationResult:
        """Show safe managed-field differences and optionally save one explicit choice."""
        from .. import config_sync, diff_view
        from ..agents import RULES_KINDS
        from ..config import DeviceConfig, absolute

        raw = self._raw_config()
        if choice is not None and choice not in diff_view.CHOICES:
            raise ValueError("diff 只接受 share、local、restore；adopt/keep/skip/remove 属于 migrate。")
        device = DeviceConfig(raw, self.local_path)
        shared: dict[str, dict[str, Any]] = {}
        local_values: dict[str, dict[str, Any]] = {}
        overridden: dict[str, set[str]] = {}
        ownership = config_sync.effective_overrides(raw, absolute(raw["state_dir"]))
        for tool in ("codex", "claude"):
            if not raw.get(tool):
                continue
            shared[tool] = {
                key: _shared_value_for(tool, key, raw, default_root=self.template_root)
                for key in raw.get(f"{tool}_keys", [])
            }
            observed = _observed_values(tool, raw)
            local_values[tool] = {
                key: ownership[tool][key] if key in ownership[tool] else observed.get(key)
                for key in raw.get(f"{tool}_keys", [])
            }
            overridden[tool] = {key for key in raw.get(f"{tool}_keys", []) if key in ownership[tool]}
        tools = [tool for tool in ("codex", "claude") if raw.get(tool)]
        rules_drift = [
            record for record in config_sync.local_drift(device)["drifting"]
            if record.get("target_kind") in RULES_KINDS
        ]
        diffs = diff_view.collect_diffs(
            shared=shared,
            local=local_values,
            tools=tools,
            rules=rules_drift,
            overrides=overridden,
        )
        summary = diff_view.non_interactive_status(diffs, choice=choice)
        outcomes: list[dict[str, Any]] = []
        if choice is not None and summary["ready"]:
            for item in diffs:
                if item.field == "rules":
                    result = config_sync.plan_rules_ownership(
                        device,
                        tool=item.tool,
                        choice=choice,
                        apply_choice=apply,
                        drifting=rules_drift,
                    )
                else:
                    result = config_sync.plan_ownership(
                        device,
                        tool=item.tool,
                        field_name=item.field,
                        value=item.local_value,
                        choice=choice,
                        apply=apply,
                    )
                outcomes.append(result)
        safe_diffs = [
            {
                "tool": item.tool,
                "field": item.field,
                "label": item.label,
                "source": item.source,
                "shared_value": item.masked().shared_value,
                "local_value": item.masked().local_value,
                "choices": list(item.choices),
            }
            for item in diffs
        ]
        data = {**summary, "diffs": safe_diffs, "outcomes": outcomes, "written": bool(apply and outcomes)}
        return ApplicationResult(data=data, detail={"diffs": diffs, "rules_drift": rules_drift, "outcomes": outcomes})

    def scan(self, *, save: bool = False) -> ApplicationResult:
        """Read-only agent inventory, optionally persisting its report."""
        from .. import agents, scan as scanner
        from ..config import absolute
        from ..layout import default_state_path
        from ..planning import source_root

        raw = self._raw_config() if self.local_path.is_file() else None
        host = agents.HostEnv.current()
        store_root = source_root(raw or {}, default_root=self.template_root)
        report = scanner.scan(host, store_root=store_root, config=raw)
        saved = None
        if save:
            state = absolute(raw["state_dir"]) if raw else default_state_path()
            saved = scanner.persist(report, state)
        data = {**report, "saved": str(saved) if saved else None}
        return ApplicationResult(data=data, detail=report)

    def migrate(
        self,
        *,
        item: str | None = None,
        choice: str | None = None,
        apply: bool = False,
    ) -> ApplicationResult:
        """Plan or apply selected rule migrations into the shared store."""
        from .. import agents, migrate
        from ..config import absolute
        from ..planning import source_root
        from ..transaction import transaction

        raw = self._raw_config()
        if choice is not None and choice not in migrate.MIGRATE_CHOICES:
            raise ValueError("migrate 只接受 adopt、keep、skip、remove")
        state = absolute(raw["state_dir"])
        plan = migrate.plan_migration(
            raw,
            local=self.local_path,
            host=agents.HostEnv.current(),
            store_root=source_root(raw, default_root=self.template_root),
            state_dir=state,
        )
        selections = migrate.select(plan, item=item, choice=choice) if (item or choice or apply) else {}
        if not apply:
            data = {
                "status": "preview",
                "items": [
                    {
                        "index": position,
                        "id": entry.id,
                        "kind": entry.kind,
                        "instance": entry.instance,
                        "path": entry.relative,
                        "lines": entry.known + len(entry.unique),
                        "unique_lines": len(entry.unique),
                        "shared_with": list(entry.shared_with),
                        "default": entry.default,
                        "choices": list(entry.choices),
                        "unique_preview": [
                            {"line_number": line.number, "text": line.text}
                            for line in entry.unique[:5]
                        ],
                    }
                    for position, entry in enumerate(plan.items, start=1)
                ],
                "blocked": plan.blocked,
                "selected": selections,
                "written": False,
            }
            return ApplicationResult(data=data, detail={"plan": plan, "selections": selections})

        changes, summary = migrate.build_changes(plan, selections, state_dir=state)
        backup = transaction(changes, state / "backups", state_root=state) if changes else None
        data = {
            "status": "applied" if changes else "no_changes",
            "summary": summary,
            "changes": len(changes),
            "backup": str(backup) if backup else None,
        }
        return ApplicationResult(data=data, detail={"plan": plan, "selections": selections})

    def detach(self, *, agent_id: str, restore_original: bool = False, apply: bool = False) -> ApplicationResult:
        """Plan or apply removal of this tool's managed content and registration."""
        from .. import migrate
        from ..config import absolute
        from ..transaction import transaction

        raw = self._raw_config()
        state = absolute(raw["state_dir"])
        changes, report = migrate.plan_detach(
            raw,
            local=self.local_path,
            instance_id=agent_id,
            state_dir=state,
            restore_original=restore_original,
        )
        backup = None
        if apply:
            backup = transaction(changes, state / "backups", state_root=state)
            migrate.remove_empty_dirs(report.get("remove_dirs"))
        data = {**report, "status": "detached" if apply else "preview", "written": bool(apply), "backup": str(backup) if backup else None}
        return ApplicationResult(data=data, detail={"plan": changes, "report": report})

    def verify_load(self, *, agent_id: str, answer: str | None = None, record: bool = False) -> ApplicationResult:
        """Prepare a fresh-session challenge or evaluate and optionally record it."""
        from .. import agents, load_check
        from ..config import absolute
        from ..planning import rules_version, read

        raw = self._raw_config()
        instance = next((entry for entry in agents.agent_instances(raw) if entry.id == agent_id), None)
        if instance is None:
            raise ValueError(f"本机没有登记这个 agent：{agent_id}；运行 status 查看已登记的 agent。")
        reason = agents.unresolved_reason(instance)
        target = agents.rules_target(instance) if reason is None else None
        if target is None:
            raise ValueError(reason or "这个 agent 没有规则入口。")
        expected = rules_version(raw, instance, default_root=self.template_root)
        on_disk = load_check.extract_version(read(target.path))
        if answer is None:
            data = {
                "status": "instructions",
                "agent": instance.id,
                "applied": on_disk is not None and on_disk == expected,
                "question": load_check.QUESTION,
            }
            return ApplicationResult(data=data, detail={"target": target, "expected": expected})
        result = load_check.evaluate(expected=expected, on_disk=on_disk, answer=answer)
        recorded = load_check.record(absolute(raw["state_dir"]), instance.id, result) if record else None
        data = {
            "status": "passed" if result["passed"] else "failed",
            "agent": instance.id,
            **result,
            "recorded": bool(recorded),
        }
        return ApplicationResult(data=data, detail={"target": target, "expected": expected})

    def declare(
        self,
        *,
        agent_id: str,
        root: str,
        entry: str | None = None,
        entry_mode: str | None = None,
        profile: str | None = None,
        apply: bool = False,
    ) -> ApplicationResult:
        """Validate and optionally register a custom or relocated agent."""
        import json

        from .. import agents
        from ..config import absolute, validate
        from ..planning import read
        from ..transaction import PlannedChanges, transaction
        from ..utils import digest, json_bytes

        raw = self._raw_config()
        spec: dict[str, Any] = {"root": root}
        if entry:
            spec["profile"] = agents.GENERIC
            spec["rules"] = {"mode": entry_mode or agents.MODE_FILE, "path": entry}
        elif profile:
            spec["profile"] = profile
        updated = json.loads(json.dumps(raw))
        if agent_id in (updated.get("agents") or {}):
            raise ValueError(f"本机已经登记了 {agent_id}；需要修改时先运行 detach 再重新声明。")
        updated.setdefault("agents", {})[agent_id] = spec
        validate(updated)
        if apply:
            state = absolute(raw["state_dir"])
            plan = PlannedChanges(
                {self.local_path: json_bytes(updated)},
                expected={self.local_path: digest(read(self.local_path))},
                state_root=state,
                metadata={"operation": "declare", "path_agents": {}},
            )
            transaction(plan, state / "backups", state_root=state)
            data = {"status": "declared", "agent": agent_id, "declaration": spec, "written": True}
        else:
            target = absolute(root)
            data = {
                "status": "preview",
                "agent": agent_id,
                "declaration": spec,
                "root_exists": target.is_dir(),
                "written": False,
            }
            plan = None
        return ApplicationResult(data=data, detail={"plan": plan, "updated_config": updated})

    def inventory(self, *, save: bool = False) -> ApplicationResult:
        """Collect configured sources and optionally persist the inventory."""
        from .. import inventory as inventory_core
        from ..config import load
        from ..transaction import SyncLock

        device = load(self.local_path)
        report = inventory_core.discover(device)
        saved = None
        if save:
            with SyncLock(device.state_dir):
                saved = inventory_core.persist_report(device, report)
        return ApplicationResult(
            data={
                "inventory_id": report["inventory_id"],
                "saved": str(saved) if saved else None,
                "summary": report["summary"],
                "sources": report["sources"],
            },
            detail=report,
        )

    def snapshots(self) -> ApplicationResult:
        """List checked snapshot metadata without exposing memory file contents."""
        from .. import snapshots as snapshots_core
        from ..config import absolute

        raw = self._raw_config()
        root = absolute(raw["memory_repo"])
        mappings = {item.get("id") for item in raw.get("memories", []) if isinstance(item, Mapping)}
        rows: list[dict[str, Any]] = []
        snapshot_dir = root / "snapshots"
        if snapshot_dir.is_symlink():
            return ApplicationResult(
                data={
                    "status": "listed",
                    "snapshots": [{"status": "blocked_symlink", "restorable": False}],
                    "memory_repository_exists": root.is_dir(),
                },
                detail=[],
            )
        for target in sorted(snapshot_dir.glob("*/*.json")):
            if target.is_symlink() or target.parent.is_symlink():
                rows.append({"snapshot_id": target.stem, "status": "blocked_symlink", "restorable": False})
                continue
            device = target.parent.name
            try:
                manifest = snapshots_core.load_snapshot(root, target.stem, device=device)
            except (OSError, ValueError, KeyError):
                rows.append({"snapshot_id": target.stem, "device_id": device, "status": "invalid", "restorable": False})
                continue
            project_id = manifest.get("project_id")
            rows.append({
                "snapshot_id": manifest["snapshot_id"],
                "device_id": manifest["device_id"],
                "created_at": manifest.get("created_at"),
                "tool": manifest.get("tool"),
                "project_id": project_id,
                "source_status": manifest.get("source_status"),
                "file_count": len(manifest.get("files", [])),
                "confirmed": snapshots_core.snapshot_confirmed(root, manifest),
                "status": "valid",
                "restorable": manifest.get("tool") == "claude" and project_id in mappings,
            })
        rows.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return ApplicationResult(data={"status": "listed", "snapshots": rows, "memory_repository_exists": root.is_dir()}, detail=rows)

    def doctor(self, *, recover: bool = False) -> ApplicationResult:
        """Inspect local sources and unfinished transactions."""
        from .. import doctor as doctor_core
        from ..config import load
        from ..transaction import recover_transactions

        device = load(self.local_path)
        if recover:
            recover_transactions(device.state_dir, action="rollback")
        report = doctor_core.run(device)
        return ApplicationResult(data=report, detail=report)

    def undo(
        self,
        *,
        list_only: bool = False,
        operation_id: str | None = None,
        index: int | None = None,
        apply: bool = False,
    ) -> ApplicationResult:
        """List or restore a previously applied local operation."""
        from .. import restore as restore_core
        from ..config import load

        state = load(self.local_path).state_dir
        if list_only or (not apply and operation_id is None and index is None):
            operations = restore_core.recent_operations(state)
            data = {
                "status": "listed",
                "count": len(operations),
                "operations": [
                    {
                        "index": position,
                        "operation_id": item.get("operation_id"),
                        "operation": item.get("operation"),
                        "created_at": item.get("created_at"),
                        "tools": item.get("tools", []),
                        "change_count": item.get("change_count", 0),
                        "backup": item.get("backup"),
                        "targets": [
                            {"path": change.get("path"), "action": "delete" if change.get("delete") else "write"}
                            for change in item.get("changes", [])
                            if isinstance(change, Mapping) and isinstance(change.get("path"), str)
                        ],
                        "statement": item["statement"],
                        "status": "COMMITTED",
                    }
                    for position, item in enumerate(operations, start=1)
                ],
            }
            return ApplicationResult(data=data, detail=operations)
        report = restore_core.restore(state, operation_id=operation_id, index=index, apply=apply)
        return ApplicationResult(data=report, detail=report)

    def project(self, *, project_id: str | None = None, handoff_id: str | None = None) -> ApplicationResult:
        """List registered projects or return the selected continuation report."""
        from ..config import absolute
        from ..onboarding import continuation_report, list_projects

        raw = self._raw_config()
        projects = list_projects(raw)
        if not projects or not project_id:
            return ApplicationResult(
                data={"status": "listed", "projects": projects},
                detail=projects,
            )
        report = continuation_report(
            raw,
            absolute(raw["memory_repo"]),
            project_id=project_id,
            handoff_id=handoff_id,
        )
        return ApplicationResult(data=report, detail=report)

    def project_setup(self, *, project_id: str, path: Path, apply: bool = False) -> ApplicationResult:
        """Map a portable project id to this device's local project directory."""
        import json
        import re

        from ..config import absolute
        from ..transaction import transaction
        from ..utils import json_bytes

        raw = self._raw_config()
        project_id = project_id.strip()
        target = absolute(path)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project_id):
            raise ValueError("项目标识仅允许小写字母、数字、下划线和连字符，并须以字母或数字开头。")
        ready = target.is_dir()
        previous = (raw.get("projects") or {}).get(project_id)
        updated = json.loads(json.dumps(dict(raw)))
        updated.setdefault("projects", {})[project_id] = str(target)
        if apply and not ready:
            raise ValueError(f"项目目录不存在：{target}")
        backup = None
        if apply:
            state = absolute(raw["state_dir"])
            backup = transaction({self.local_path: json_bytes(updated)}, state / "backups", state_root=state)
        return ApplicationResult(
            data={
                "status": "mapped" if apply else "preview",
                "ready": ready,
                "project_id": project_id,
                "path": str(target),
                "previous_path": previous,
                "written": bool(apply),
                "backup": str(backup) if backup else None,
            },
            detail={"updated_config": updated},
        )

    def memory_setup(
        self,
        *,
        disable: bool = False,
        apply: bool = False,
        selections: list[Mapping[str, Any]] | None = None,
    ) -> ApplicationResult:
        """Inspect, enable, or disable supported memory mappings."""
        from ..config import absolute
        from ..onboarding import candidate_sources, disable_memory, plan_memory_enable
        from ..transaction import transaction
        from ..utils import json_bytes

        raw = self._raw_config()
        if disable:
            report = disable_memory(raw)
            updated = {key: value for key, value in raw.items() if key != "memories"}
            updated["memories"] = []
            if not apply:
                return ApplicationResult(
                    data={**report, "status": "preview", "written": False},
                    detail={"updated_config": updated},
                )
            state = absolute(raw["state_dir"])
            backup = transaction({self.local_path: json_bytes(updated)}, state / "backups", state_root=state)
            return ApplicationResult(data={**report, "written": True, "backup": str(backup) if backup else None}, detail={"updated_config": updated})
        rows = candidate_sources(raw)
        if not apply:
            selection_preview = plan_memory_enable(config=raw, selections=selections) if selections is not None else None
            return ApplicationResult(
                data={"status": "preview", "sources": rows, "mappings": raw.get("memories", []), "selection_preview": selection_preview, "written": False},
                detail={"sources": rows, "selection_preview": selection_preview},
            )
        selected = selections if selections is not None else [
            {"path": row["path"], "id": row["project_id"] or None}
            for row in rows
            if row["enableable"] and row["tool"] == "claude"
        ]
        report = plan_memory_enable(config=raw, selections=selected)
        if report["status"] != "ready":
            return ApplicationResult(data=report, detail={"updated_config": None})
        updated = dict(raw)
        merged = {entry["id"]: entry for entry in raw.get("memories", [])}
        for mapping in report["mappings"]:
            merged[mapping["id"]] = mapping
        updated["memories"] = [merged[key] for key in sorted(merged)]
        state = absolute(raw["state_dir"])
        backup = transaction({self.local_path: json_bytes(updated)}, state / "backups", state_root=state)
        return ApplicationResult(data={**report, "written": True, "backup": str(backup) if backup else None}, detail={"updated_config": updated})

    def restore_snapshot(self, *, snapshot_id: str, apply: bool = False) -> ApplicationResult:
        """Plan or apply a supported Claude memory snapshot to its local mapping."""
        from .. import snapshots
        from ..config import absolute
        from ..transaction import transaction

        raw = self._raw_config()
        memory_root = absolute(raw["memory_repo"])
        manifest = snapshots.load_snapshot(memory_root, snapshot_id)
        if manifest.get("tool") == "codex":
            raise ValueError("Codex snapshots are references only and cannot be applied to native Codex memory")
        project_id = manifest.get("project_id") or manifest.get("scope")
        item = next((entry for entry in raw.get("memories", []) if entry.get("id") == project_id), None)
        if item is None:
            raise ValueError(f"No memory mapping configured for project: {project_id}")
        state = absolute(raw["state_dir"])
        changes = snapshots.restore_snapshot(memory_root, manifest, absolute(item["path"]))
        paths = [str(path) for path in changes]
        if apply and changes:
            transaction(changes, state / "backups", state_root=state)
        data = {
            "status": "applied" if apply else "preview",
            "snapshot_id": snapshot_id,
            "changes": len(changes),
            "paths": paths,
            "written": bool(apply and changes),
        }
        return ApplicationResult(data=data, detail=changes)

    def finish(
        self,
        *,
        project_id: str,
        handoff_file: Path | None = None,
        handoff_text: str | None = None,
        apply: bool = False,
    ) -> ApplicationResult:
        """Create a handoff and memory snapshot, or return a read-only readiness preview."""
        from .continuation import finish_apply, finish_preview

        if (handoff_file is None) == (handoff_text is None):
            raise ValueError("Provide exactly one of handoff_file or handoff_text.")
        config = self._raw_config()
        report = (
            finish_apply(config, project_id, Path(handoff_file) if handoff_file is not None else None, handoff_text=handoff_text, default_root=self.template_root)
            if apply
            else finish_preview(config, project_id, Path(handoff_file) if handoff_file is not None else None, handoff_text=handoff_text, default_root=self.template_root)
        )
        return ApplicationResult(data=report, detail=report)

    def start(self, *, project_id: str, handoff_id: str, apply: bool = False) -> ApplicationResult:
        """Fetch and reconcile a registered handoff against this device's memory baseline."""
        from ..config import absolute
        from .continuation import start as start_continuation

        config = self._raw_config()
        report = start_continuation(
            config,
            project_id,
            handoff_id,
            apply=apply,
            state=absolute(config["state_dir"]),
            default_root=self.template_root,
        )
        plan = report.pop("paths", [])
        return ApplicationResult(data=report, detail={"paths": plan})
