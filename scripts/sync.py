"""Cross-platform rules, configuration, memory and handoff synchronization."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sync_core.config import absolute as config_absolute
from sync_core.config import load as load_config
from sync_core.config_sync import ConfigSyncError, OwnershipError
from sync_core.handoff import code_facts, configuration_facts, register_project, save_handoff, start_report, validate_handoff
from sync_core.inventory import discover, persist_report
from sync_core.merge import merge as merge_maps
from sync_core.merge import three_way_merge
from sync_core.snapshots import create_snapshot, load_snapshot, mark_head_confirmed, restore_snapshot, snapshot_files
from sync_core.transaction import PlannedChanges, SyncLock, recover_transactions, transaction as apply_transaction
from sync_core.utils import digest as content_digest


# Kept here for scripts and tests that used the original module API.
BEGIN = b"<!-- ai-config:begin -->"
END = b"<!-- ai-config:end -->"
merge = merge_maps
absolute = config_absolute


class SyncCommandError(RuntimeError):
    """A user-actionable sync result with a stable CLI exit code."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status = {EXIT_INCOMPLETE: "incomplete", EXIT_PENDING: "pending", EXIT_CONFLICT: "conflict"}.get(code, "error")


EXIT_INCOMPLETE = 2
EXIT_PENDING = 3
EXIT_CONFLICT = 4


def read(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ValueError(f"Symlink requires manual migration: {path}")
    return path.read_bytes() if path.exists() else None


def write(path: Path, data: bytes | None) -> None:
    from sync_core.transaction import write_file
    write_file(path, data)


def files(root: Path, exclude: list[str] | None = None) -> dict[str, bytes]:
    """Compatibility wrapper for the shared memory-source reader."""
    from sync_core.memory_io import files as read_files

    return read_files(root, exclude)


def digest(data: bytes | None) -> str | None:
    return content_digest(data)


def stable_files(root: Path, exclude: list[str] | None = None, *, attempts: int = 3, interval: float = 0.05) -> dict[str, bytes]:
    """Compatibility wrapper for the shared stable memory-source reader."""
    from sync_core.memory_io import stable_files as read_stable_files

    return read_stable_files(root, exclude, attempts=attempts, interval=interval)


def transaction(changes: Mapping[Path, bytes | None], backup_root: Path, **kwargs: Any) -> Path | None:
    """Compatibility wrapper using this module's write function for old callers."""
    return apply_transaction(changes, backup_root, writer=write, **kwargs)


def _source_root(config: Mapping[str, Any] | None = None) -> Path:
    """Compatibility wrapper for callers of the original script API."""
    from sync_core.planning import source_root

    return source_root(config, default_root=ROOT)


def _body(config: Mapping[str, Any] | None = None, topics: tuple[str, ...] | None = None) -> bytes:
    from sync_core.planning import render_body

    return render_body(config, topics, default_root=ROOT)


def _rules_version(config: Mapping[str, Any], instance: Any = None) -> str | None:
    from sync_core.planning import rules_version

    return rules_version(config, instance, default_root=ROOT)


def _rules_body(config: Mapping[str, Any], instance: Any = None) -> bytes:
    from sync_core.planning import rules_body

    return rules_body(config, instance, default_root=ROOT)


def _rules_plan(config: dict[str, Any], state: Path) -> PlannedChanges:
    from sync_core.planning import rules_plan

    return rules_plan(config, state, default_root=ROOT)


def _owned_file_result(
    config: Mapping[str, Any],
    state: Path,
    tool: str,
    target: Path,
    current: bytes | None,
    body: bytes,
    previous: Mapping[str, Any] | None,
) -> bytes | None:
    from sync_core.planning import _owned_file_result as owned_file_result

    return owned_file_result(config, state, tool, target, current, body, previous)


def _config_plan(config: dict[str, Any], state: Path) -> PlannedChanges:
    from sync_core.planning import config_plan

    return config_plan(config, state, default_root=ROOT)


def _baseline(marker: Path) -> dict[str, str]:
    from sync_core.planning import memory_baseline

    return memory_baseline(marker)


def _memory_plan(config: dict[str, Any], state: Path) -> PlannedChanges:
    from sync_core.planning import memory_plan

    return memory_plan(config, state, default_root=ROOT)


def plan(config: dict[str, Any], mode: str) -> PlannedChanges:
    """Compatibility entry point delegating to the client-callable service."""
    from sync_core.application.service import plan_local_changes

    return plan_local_changes(config, mode, template_root=ROOT)


def _project_path(config: dict[str, Any], project_id: str) -> Path:
    from sync_core.application.continuation import project_path

    return project_path(config, project_id)


def _mapping(config: dict[str, Any], project_id: str) -> dict[str, Any]:
    from sync_core.application.continuation import memory_mapping

    return memory_mapping(config, project_id)


def _snapshot_for_finish(config: dict[str, Any], project_id: str) -> dict[str, Any]:
    from sync_core.application.continuation import snapshot_for_finish

    return snapshot_for_finish(config, project_id)


def _config_facts(config: dict[str, Any] | None = None) -> dict[str, Any]:
    from sync_core.application.continuation import config_facts

    return config_facts(config or {}, default_root=ROOT)

def _quick_device_config() -> dict[str, Any]:
    from sync_core.application.service import generated_device_config

    return generated_device_config()


def _generated_device_config(local: Path) -> dict[str, Any]:
    """Device configuration used when the user has not created one yet.

    Field selection is read from the detected tools rather than assuming the
    complete allowlist, so a rules-only device stays rules-only.
    """
    return _quick_device_config()


def _quick_setup(config: dict[str, Any], local: Path, *, apply: bool, generated: bool) -> dict[str, Any]:
    """Compatibility adapter for the client-callable quick-setup operation."""
    from sync_core.application import ApplicationService

    return ApplicationService(local, template_root=ROOT).quick_setup(
        config, generated=generated, apply=apply
    ).data


def _run_finish(config: dict[str, Any], project_id: str, handoff_file: Path) -> dict[str, Any]:
    """Compatibility wrapper for the client-callable finish operation."""
    from sync_core.application.continuation import finish_apply

    return finish_apply(config, project_id, handoff_file, default_root=ROOT)


def _finish_preview(config: dict[str, Any], project_id: str, handoff_file: Path) -> dict[str, Any]:
    """Compatibility wrapper for the client-callable finish preview."""
    from sync_core.application.continuation import finish_preview

    return finish_preview(config, project_id, handoff_file, default_root=ROOT)

def _memory_setup_command(config: dict[str, Any], args: argparse.Namespace, local: Path) -> None:
    """Optional memory onboarding; never blocks configuration sync."""
    from sync_core.application import ApplicationService
    from sync_core.onboarding import describe_sources

    operation = ApplicationService(local, template_root=ROOT).memory_setup(
        disable=args.disable, apply=args.apply
    )
    if args.disable:
        print(json.dumps(operation.data, ensure_ascii=False, indent=2))
        return
    if not args.apply:
        print("记忆来源：")
        for line in describe_sources(operation.detail):
            print("  " + line)
        print("\n以上为只读盘点。加 --apply 并指定要启用的来源才会写入映射。")
        return
    if operation.data.get("status") == "empty":
        print("没有可启用的 Claude 记忆来源；配置同步不受影响。")
        return
    if operation.data.get("status") != "ready":
        print(json.dumps(operation.data, ensure_ascii=False, indent=2))
        print("没有写入任何映射。")
        return
    print(json.dumps(operation.data, ensure_ascii=False, indent=2))


def _project_command(config: dict[str, Any], args: argparse.Namespace) -> None:
    """Project continuation without typing internal ids."""
    from sync_core.application import ApplicationService

    operation = ApplicationService(args.local, template_root=ROOT).project(
        project_id=args.project, handoff_id=args.handoff_id
    )
    projects = operation.detail
    if not projects:
        print("还没有登记任何项目；先运行一次接续相关命令或完成 finish。")
        return
    if not args.project:
        print("可接续的项目：")
        for position, row in enumerate(projects, start=1):
            memory = "有记忆映射" if row["has_memory"] else "无记忆映射"
            print(f"  {position}. {row['name']}（{row['project_id']}，{memory}）")
        print("\n使用 --project <项目标识> 查看最近可用的交接。")
        return
    report = operation.data
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if not report.get("ready"):
        print(f"暂不能接续：{report.get('reason') or '资料不完整'}")
        for key, value in (report.get("checks") or {}).items():
            if not value:
                print(f"  未通过：{key}")
        return
    print(f"项目：{report['project_id']}")
    print(f"使用交接：{report['handoff_id']}（创建于 {report.get('created_at')}）")
    print(f"目标：{report.get('goal')}")
    print(f"已完成：{report.get('completed')}")
    print(f"下一步：{report.get('next_step')}")
    print(f"尚未完成：{report.get('remaining')}")
    print(f"版本：{report.get('version')}")
    if report.get("unsynced"):
        print("未同步项：" + "、".join(str(item) for item in report["unsynced"]))


def _print_changes(changes: Mapping[Path, bytes | None]) -> None:
    for path, data in changes.items():
        print(f"{'DELETE' if data is None else 'WRITE'} {path}")


def _render_doctor(report: Mapping[str, Any]) -> None:
    """Chinese diagnostic summary; the raw codes stay available via --json."""
    checks = report.get("checks", {}) or {}
    print(f"设备：{report.get('device_id')}")
    print(f"总体：{'正常' if report.get('ok') else '需要处理'}")
    print("")

    inventory = checks.get("inventory", {}) or {}
    if inventory:
        print(f"来源盘点：共 {inventory.get('total', 0)} 个，可用 {inventory.get('ready', 0)} 个"
              f"，待映射 {inventory.get('pending_mapping', 0)} 个，不可用 {inventory.get('unavailable', 0)} 个")

    transactions = checks.get("transactions", []) or []
    if transactions:
        print(f"事务记录：{len(transactions)} 条")
    else:
        print("事务记录：无未完成事务")
    print(f"记忆仓库：{'存在' if checks.get('memory_repository_exists') else '尚未创建（未启用记忆时属正常）'}")

    if report.get("issues"):
        print("")
        print("需要处理：")
        for item in report["issues"]:
            print(f"  - {_translate_doctor(item)}")
    if report.get("warnings"):
        print("")
        print("提示：")
        for item in report["warnings"]:
            print(f"  - {_translate_doctor(item)}")
    print("")
    if report.get("ok"):
        print("结论：未发现问题，可以继续同步。")
    else:
        print("结论：请按上面列出的项目处理后重试；不要只删除锁文件。")


def _translate_doctor(text: str) -> str:
    """Translate the known doctor findings; unknown text is shown verbatim."""
    known = {
        "A sync operation is currently running": "已有同步操作正在运行，请等待它结束。",
        "A stale sync lock is present; the next operation can recover it": "存在过期的同步锁，下一次操作会自动处理。",
        "An unreadable transaction journal requires manual review": "有事务日志无法读取，需要人工检查。",
        "Memory repository does not exist yet": "记忆仓库尚未创建；未启用记忆时属正常。",
        "Memory repository is not a Git repository yet": "记忆仓库还不是 Git 仓库，需要先初始化或添加远端。",
        "Memory repository has unpublished local changes": "记忆仓库有未发布的本地修改，需要先处理再推送。",
        "Memory Git transport is pending; retry after preserving the local commit": "记忆推送处于待处理状态；请保留本地提交后重试。",
        "Transport state is unreadable": "传输状态文件无法读取。",
    }
    if text in known:
        return known[text]
    match = re.fullmatch(r"(\d+) incomplete transaction\(s\) require rollback review", text)
    if match:
        return f"有 {match.group(1)} 个未完成事务需要确认回滚。"
    match = re.fullmatch(r"Snapshot head hash mismatch: (.+)", text)
    if match:
        return f"快照头哈希不匹配：{match.group(1)}"
    match = re.fullmatch(r"Snapshot head is not remotely confirmed: (.+)", text)
    if match:
        return f"快照头尚未在远端确认：{match.group(1)}"
    match = re.fullmatch(r"Invalid snapshot head: (.+)", text)
    if match:
        return f"快照头无效：{match.group(1)}"
    match = re.fullmatch(r"(.+): (missing|unreadable|blocked_secret|pending_mapping|unsupported|path_collision)", text)
    if match:
        label = {
            "missing": "来源目录不存在",
            "unreadable": "来源无法读取",
            "blocked_secret": "发现疑似凭据，已阻止同步（不输出匹配内容）",
            "pending_mapping": "来源尚未确认映射",
            "unsupported": "来源含不支持的文件类型",
            "path_collision": "来源存在大小写或 Unicode 冲突",
        }[match.group(2)]
        return f"{match.group(1)}：{label}"
    match = re.fullmatch(r"(.+): not configured", text)
    if match:
        return f"{match.group(1)}：尚未配置"
    return text


def _config_sync_command(config: dict[str, Any], args: argparse.Namespace, local: Path) -> None:
    """Render the client-callable service's configuration reconciliation result."""
    from sync_core.application import ApplicationService
    from sync_core.config_sync import ConfigSyncError

    def checkpoint(stage: str) -> None:
        if args.verbose and not args.json:
            print(f"[阶段] {stage}")

    try:
        report = ApplicationService(local, template_root=ROOT).sync(
            apply=args.apply,
            fetch=args.fetch,
            publish=args.publish,
            checkpoint=checkpoint,
        ).data
    except ConfigSyncError as error:
        from sync_core import messages
        code = error.code or {"fetch": "E2001", "publish": "E2001", "resolve": "E3001", "apply": "E3003", "verify": "E3002"}.get(error.stage, "E9001")
        if error.exit_code == EXIT_CONFLICT and error.stage in {"fetch", "publish"}:
            code = "E2002"
        message = messages.get(code, detail=str(error))
        if args.json:
            payload = {**message.as_json(), "stage": error.stage, "status": "failed"}
            print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        else:
            print(messages.render(message, verbose=args.verbose), file=sys.stderr)
        raise SystemExit(error.exit_code) from error

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        _render_sync_report(report)
    # A preview is not a failure, but it is also not an applied state.
    if report.get("status") == "preview":
        raise SystemExit(2 if report.get("drifting") else 0)
    _report_receipt_outcome(report, args)


def _report_receipt_outcome(report: Mapping[str, Any], args: argparse.Namespace) -> None:
    """A receipt that could not be uploaded is a warning, never a fake success."""
    from sync_core import messages

    receipt = report.get("receipt") or {}
    if receipt.get("status") != "pending":
        return
    message = messages.get("E5001", detail=str(receipt.get("detail") or ""))
    if args.json:
        print(json.dumps({**message.as_json(), "stage": "receipt", "status": "pending"}, ensure_ascii=False), file=sys.stderr)
    else:
        print(messages.render(message, verbose=args.verbose), file=sys.stderr)
    raise SystemExit(EXIT_PENDING)


def _render_pipeline(report: Mapping[str, Any]) -> list[str]:
    """Render 下载 / 发布 / 上报 as separate statements with their real outcome."""
    lines: list[str] = []
    remote = report.get("remote") or {}
    status = remote.get("status")
    commit = str(remote.get("commit") or "")[:12]
    if status == "updated":
        lines.append(f"下载共享配置：已更新到 {commit}")
    elif status == "up_to_date":
        lines.append(f"下载共享配置：已是最新（{commit}）")
    elif status in {"diverged", "blocked"}:
        lines.append("下载共享配置：未完成，" + str(remote.get("detail") or ""))
    elif status in {"not_configured", "skipped"}:
        lines.append("下载共享配置：" + str(remote.get("detail") or "未下载"))

    publish = report.get("publish") or {}
    pstatus = publish.get("status")
    pcommit = str(publish.get("commit") or "")[:12]
    if pstatus == "published":
        lines.append(f"远端发布：已发布 {len(publish.get('files', []))} 个共享文件（{pcommit}）")
    elif pstatus == "saved_locally":
        lines.append("远端发布：已提交在本机，未推送。" + str(publish.get("detail") or ""))
    elif pstatus == "pending":
        lines.append(
            f"远端发布：有 {len(publish.get('files', []))} 个共享文件只保存在本机；"
            "运行 sync --publish --apply 发布到配置源远端。"
        )
    elif pstatus == "nothing_to_publish":
        lines.append("远端发布：没有待发布的共享修改")
    elif pstatus == "not_configured":
        lines.append("远端发布：配置源不是 Git 仓库，已跳过")
    elif pstatus == "skipped":
        lines.append("远端发布：未加 --publish，共享修改只保存在本机")

    receipt = report.get("receipt") or {}
    rstatus = receipt.get("status")
    if rstatus == "uploaded":
        lines.append("状态上报：已上报到共享回执分支")
    elif rstatus == "pending":
        lines.append("状态上报：尚未上报，" + str(receipt.get("detail") or ""))
    elif rstatus == "not_configured":
        lines.append("状态上报：" + str(receipt.get("detail") or "未配置，已跳过"))
    return lines


def _render_unresolved(report: Mapping[str, Any]) -> None:
    from sync_core.agents import label

    for item in report.get("unresolved") or []:
        print(f"提示：{label(item['instance'])} 暂无规则入口，本次未写入：{item['reason']}（E1003）")


def _render_sync_report(report: Mapping[str, Any]) -> None:
    _render_unresolved(report)
    status = report.get("status")
    if status == "preview":
        changes = report.get("changes", 0)
        if changes:
            print(f"将要应用 {changes} 处共享配置变更：")
            for path in report.get("paths", []):
                print(f"  {path}")
        else:
            print("本机受管配置已与共享值一致，没有需要写入的变化。")
        for line in _render_pipeline(report):
            print(line)
        if report.get("drifting"):
            print("")
            print("以下目标文件被本机修改过，应用前需要先决定归属：")
            for target in report["drifting"]:
                print(f"  {target}")
            print("运行 sync 时先处理这些差异，或用 diff 查看并选择处理方式。")
        print("")
        print("这是预览，没有写入任何文件；加 --apply 后才会应用。")
        print("预览不代表已经应用；零变更预览也不代表已生效。")
        return
    if status == "applied":
        changes = report.get("changes", 0)
        if changes:
            print(f"本机应用：已应用 {changes} 处共享配置变更。")
        else:
            print("本机应用：没有需要写入的变化；已重新核对目标文件。")
        for line in _render_pipeline(report):
            print(line)
        if not report.get("verified"):
            print("未能确认所有目标文件都已是期望内容，未记录成功；请运行 status 查看详情。")
        elif report.get("requires_restart"):
            print("本机目标文件已重新读取并核对一致。")
            print("工具需要启动新会话才会加载这些设置。")
        return
    print(f"同步状态：{status}")


def _status_command(config: dict[str, Any], args: argparse.Namespace, local: Path) -> None:
    """Chinese status overview; memory and handoff are listed separately."""
    from sync_core.application import ApplicationService
    from sync_core.receipts import device_summary
    from sync_core import messages

    result = ApplicationService(local, template_root=ROOT).status().data
    state = result["state"]
    receipts = result["receipts"]
    config_cap = state["capabilities"]["config"]
    lines = [
        f"设备：{state['device_id']}",
        f"配置源：{state['source'].get('identity') or '未设置'}",
        f"共享版本：{(state['managed'].get('last_applied_version') or '未知')[:12]}",
        f"本机配置状态：{_status_label(config_cap['status'])}",
    ]
    from sync_core.agents import RULES_KINDS, label
    from sync_core.config_sync import unresolved_agents
    from sync_core.load_check import STATE_LABELS

    for target in state["managed"].get("targets", []):
        fields = "、".join(target.get("fields", [])) or "（无受管字段）"
        line = f"  {label(str(target.get('tool')))} · {Path(str(target.get('target'))).name}：{_status_label(str(target.get('status')))}（受管：{fields}）"
        if target.get("target_kind") in RULES_KINDS:
            line += f"；规则版本 {target.get('rules_version') or '未知'}，加载核验：{STATE_LABELS.get(str(target.get('load_check')), '未核验')}"
        lines.append(line)
    for item in unresolved_agents(config):
        lines.append(f"  {label(item['instance'])}：暂无规则入口，{item['reason']}（E1003）")
    lines.append(f"最近成功应用时间：{state['managed'].get('last_applied_at') or '尚未应用'}")
    lines.append(f"最近核对时间：{state['managed'].get('last_verified_at')}")
    lines.append("")
    memory = state["capabilities"]["memory"]
    handoff = state["capabilities"]["handoff"]
    lines.append(f"记忆同步：{'已启用' if memory['enabled'] else '未启用'}")
    lines.append(f"项目接续：{'已启用' if handoff['enabled'] else '未启用'}")
    lines.append("")
    lines.append("其他设备：")
    if receipts:
        for row in device_summary(receipts, this_device=state["device_id"]):
            marker = "（本机）" if row["is_this_device"] else ""
            lines.append(f"  {row['device_id']}{marker}：{row['statement']}")
    else:
        lines.append("  暂无其他设备回执。")
    lines.append("")
    next_step = result["next_step"]
    lines.append("下一步：" + next_step)
    if args.json:
        print(json.dumps({
            "state": state,
            "receipts": receipts,
            "next_step": next_step,
        }, ensure_ascii=False, indent=2))
        return
    print("\n".join(lines))


_STATUS_LABELS = {
    "not_configured": "未设置",
    "pending_sync": "待同步",
    "applied": "已应用",
    "local_modified": "存在本机修改",
    "conflict": "冲突",
    "offline": "离线",
    "apply_failed": "应用失败",
    "restart_required": "需要重启工具会话",
}


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, f"未知（{status}）")


def _scan_command(args: argparse.Namespace, local: Path) -> None:
    """Read-only inventory of every agent; works before any device.json exists."""
    from sync_core.application import ApplicationService
    from sync_core import scan as scanner

    result = ApplicationService(local, template_root=ROOT).scan(save=args.apply)
    if args.json:
        print(json.dumps(result.data, ensure_ascii=False))
        return
    print(scanner.render(result.detail))
    if result.data["saved"]:
        print(f"报告已保存：{result.data['saved']}")


def _migrate_error(error: Exception, args: argparse.Namespace, code: int) -> None:
    if args.json:
        print(json.dumps({"status": "failed", "reason": str(error)}, ensure_ascii=False))
    else:
        print(f"无法继续：{error}", file=sys.stderr)
    raise SystemExit(code)


def _migrate_command(config: dict[str, Any], args: argparse.Namespace, local: Path) -> None:
    """Preview or apply the migration of existing agent rules into the store."""
    from sync_core import migrate
    from sync_core.application import ApplicationService

    try:
        operation = ApplicationService(local, template_root=ROOT).migrate(
            item=args.item, choice=args.choice, apply=args.apply
        )
    except migrate.MigrationError as error:
        _migrate_error(error, args, error.exit_code)
    except ValueError as error:
        _migrate_error(error, args, EXIT_INCOMPLETE)

    plan = operation.detail["plan"]
    selections = operation.detail["selections"]
    if not args.apply:
        if args.json:
            print(json.dumps(operation.data, ensure_ascii=False))
            return
        print(migrate.render_plan(plan))
        for item_id, choice in selections.items():
            print(f"\n将要对 {item_id} 执行：{migrate.CHOICE_LABELS[choice]}（预览，未写入；加 --apply 执行）")
        return
    if args.json:
        print(json.dumps(operation.data, ensure_ascii=False))
        return
    summary = operation.data["summary"]
    if not operation.data["changes"]:
        print("没有需要执行的迁入动作。独有内容需要用 --item 与 --choice 单独处理。")
        return
    labels = {"registered": "已登记", "removed": "已移除重复段落", "adopted": "已采纳到配置库", "kept": "已保留", "skipped": "已记住不登记"}
    for key, label in labels.items():
        if summary.get(key):
            print(f"{label}：{len(summary[key])} 项")
    if summary.get("adopted"):
        print("采纳的内容写入了配置库 common/imported.md；运行 sync --publish --apply 发布给其他设备。")
    print("所有改动已先备份，可以用 undo 撤销；运行 sync --apply 把配置库应用到各 agent。")


def _detach_command(config: dict[str, Any], args: argparse.Namespace, local: Path) -> None:
    """Take one agent out of ai-config's management."""
    from sync_core import migrate
    from sync_core.application import ApplicationService

    if not args.agent:
        _migrate_error(ValueError("detach 需要用 --agent 指定要退出接管的 agent"), args, EXIT_INCOMPLETE)
    try:
        operation = ApplicationService(local, template_root=ROOT).detach(
            agent_id=args.agent, restore_original=args.restore_original, apply=args.apply
        )
    except migrate.MigrationError as error:
        _migrate_error(error, args, error.exit_code)
    report = operation.detail["report"]
    if args.json:
        print(json.dumps(operation.data, ensure_ascii=False))
    else:
        done = "已" if args.apply else "将"
        print(f"{report['name']}（{report['instance']}）：")
        for item in report["files"]:
            action = "删除 ai-config 创建的文件" if item["action"] == "delete" else "移除 ai-config 受管区块，保留你自己的内容"
            print(f"  {done}{action}：{item['path']}")
        for path in report["restored"]:
            print(f"  {done}恢复迁入前的原始内容：{path}")
        for conflict in report["conflicts"]:
            print(f"  未恢复：{conflict['path']}（{conflict['reason']}）")
        print(f"  {done}从本机配置中取消登记。")
        if not args.apply:
            print("以上为预览，未写入任何文件；加 --apply 后执行，执行前会先备份，可以用 undo 撤销。")
    if args.apply and report["conflicts"]:
        raise SystemExit(EXIT_CONFLICT)


def _verify_load_command(config: dict[str, Any], args: argparse.Namespace, local: Path) -> None:
    """Challenge-response proof that an agent loaded the rules in a new session."""
    from sync_core import agents, load_check, messages
    from sync_core.application import ApplicationService

    if not args.agent:
        _migrate_error(ValueError("verify-load 需要用 --agent 指定要核验的 agent"), args, EXIT_INCOMPLETE)
    try:
        operation = ApplicationService(local, template_root=ROOT).verify_load(
            agent_id=args.agent, answer=args.answer, record=args.apply
        )
    except ValueError as error:
        _migrate_error(error, args, EXIT_INCOMPLETE)
    data = operation.data
    target = operation.detail["target"]
    name = agents.label(args.agent)
    if args.answer is None:
        if args.json:
            print(json.dumps(data, ensure_ascii=False))
            return
        print(f"核验 {name} 是否真的加载了 ai-config 规则：")
        print(f"  1. 本机规则入口：{target.path}（{'已是当前版本' if data['applied'] else '还不是当前版本，请先运行 sync --apply'}）")
        print(f"  2. 在 {name} 中开启一个新会话，发送：{load_check.QUESTION}")
        print(f"  3. 把它的回答原样传回：verify-load --agent {args.agent} --answer \"<回答>\" --apply")
        print("版本号由规则内容计算得出，无法猜出；答对即证明该会话确实读取了这个入口。")
        return
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
    elif data["passed"]:
        print(f"{name}：加载核验通过（规则版本 {data['expected']}）。")
    else:
        print(f"{name}：加载核验未通过。期望版本 {data['expected']}，回答中的版本 {data['answered'] or '（没有找到）'}。")
        print("  " + load_check.REASON_LABELS.get(str(data["reason"]), str(data["reason"])))
    if not args.json and not args.apply:
        print("（结果未记录；加 --apply 才会把核验结果记到本机状态，status 中才会显示。）")
    if not data["passed"]:
        if not args.json:
            print(messages.render(messages.get("E6001")), file=sys.stderr)
        raise SystemExit(EXIT_INCOMPLETE)


def _declare_command(config: dict[str, Any], args: argparse.Namespace, local: Path) -> None:
    """Register one agent instance without editing device.json by hand."""
    from sync_core.application import ApplicationService

    if not args.agent or not args.root:
        _migrate_error(ValueError("declare 需要 --agent <标识> 和 --root <配置目录>"), args, EXIT_INCOMPLETE)
    try:
        operation = ApplicationService(local, template_root=ROOT).declare(
            agent_id=args.agent,
            root=args.root,
            entry=args.entry,
            entry_mode=args.entry_mode,
            profile=args.profile,
            apply=args.apply,
        )
    except ValueError as error:
        code = EXIT_CONFLICT if "已经登记" in str(error) else EXIT_INCOMPLETE
        _migrate_error(error, args, code)
    data = operation.data
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
        return
    if not args.apply:
        print(f"将登记 {args.agent}：{json.dumps(data['declaration'], ensure_ascii=False)}")
        if not data["root_exists"]:
            print("注意：该目录目前不存在；目录出现之前不会写入任何文件，也不会自动创建。")
        print("以上为预览，未写入任何文件；加 --apply 后写入本机配置（先备份，可以用 undo 撤销）。")
        return
    print(f"已登记 {args.agent}。运行 sync 预览要写入的规则，确认后加 --apply；之后可以用 verify-load 核验是否真的被读取。")


def _setup_command(args: argparse.Namespace, local: Path) -> None:
    from sync_core import messages, store as stores
    from sync_core.application import ApplicationService
    from sync_core.config import absolute
    from sync_core.layout import default_state_path
    from sync_core.wizard import describe_detected, describe_plan

    service = ApplicationService(local, template_root=ROOT)
    try:
        operation = service.setup(
            store_path=absolute(args.store) if args.store else None,
            remote=args.remote,
            state_dir=absolute(args.state_dir) if args.state_dir else default_state_path(),
            memory_repo=absolute(args.memory_repo) if args.memory_repo else Path.home() / "ai-memory",
            apply=args.apply,
        )
    except stores.StoreError as error:
        _migrate_error(error, args, error.exit_code)
    report = operation.data
    detected = report["detected"]
    if not args.apply:
        store_plan = report.get("store")
        if args.json:
            print(json.dumps({
                "status": "preview",
                "store": store_plan,
                "ready": bool(report.get("ready")),
                "system": detected.get("system"),
                "python": detected.get("dependencies", {}).get("python", {}).get("version"),
                "git": detected.get("dependencies", {}).get("git", {}).get("ok"),
                "tools": [
                    {
                        "tool": tool["tool"],
                        "installed": tool["installed"],
                        "root": tool.get("root"),
                        "root_origin": tool.get("root_origin"),
                        "root_exists": tool.get("root_exists"),
                    }
                    for tool in detected["tools"]
                ],
                "guidance": detected.get("guidance", []),
                "written": False,
            }, ensure_ascii=False))
            return
        print("环境检测结果：")
        for line in describe_detected(detected):
            print("  " + line)
        for item in detected.get("guidance", []):
            print(f"[{item['code']}] {item['message']}")
            print(f"  下一步：{item['action']}")
        if store_plan:
            print(f"配置库：{store_plan['path']} —— {store_plan['detail']}")
        print("以上为只读检测，未写入任何文件。加 --apply 才会写入本机配置。")
        print("想看完整的识别结果（仅识别的 agent、受保护文件、skills）请运行 scan；已有规则可用 migrate 迁入。")
        return

    if report.get("status") != "configured":
        code = "E1002" if not report.get("tools") else "E2001" if args.remote and not detected.get("dependencies", {}).get("git", {}).get("ok") else "E9001"
        message = messages.get(code)
        if args.json:
            print(json.dumps(messages.json_error(message), ensure_ascii=False))
        else:
            print(messages.render(message), file=sys.stderr)
        raise SystemExit(2)
    config = report["config"]
    if args.json:
        print(json.dumps({
            "status": "configured",
            "config_path": report["config_path"],
            "backup": report["backup"],
            "tools": report["tools"],
            "scope": "rules_only",
            "written": True,
            "note": report["note"],
        }, ensure_ascii=False))
        return
    print("即将写入的本机配置：")
    for line in describe_plan(config):
        print("  " + line)
    print(f"本机配置已写入：{report['config_path']}")
    if report.get("backup"):
        print(f"原有配置已保留：{report['backup']}")
    print("这不代表其他设备已经同步。")

def _restore_command(config: dict[str, Any], args: argparse.Namespace) -> None:
    from sync_core import restore as restore_core
    from sync_core.application import ApplicationService

    try:
        operation = ApplicationService(args.local, template_root=ROOT).undo(
            list_only=args.list,
            operation_id=args.operation,
            index=args.index,
            apply=args.apply,
        )
    except restore_core.RestoreError as error:
        if args.json:
            print(json.dumps({"status": "failed", "reason": str(error), "applied": False}, ensure_ascii=False))
            raise SystemExit(2) from error
        print(f"无法恢复：{error}", file=sys.stderr)
        raise SystemExit(2) from error
    report = operation.data
    if report.get("status") == "listed":
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
            return
        operations = operation.detail
        if not operations:
            print("没有可恢复的配置应用记录。")
            return
        print("最近的配置应用记录：")
        for position, item in enumerate(operations, start=1):
            print(f"  {position}. {item['statement']}")
        print("\n使用 --index <序号> 或 --operation <ID> 选择要撤销的记录。")
        return
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
        return
    paths = report.get("paths", [])
    done = report.get("status") == "restored"
    if not paths:
        print("没有需要恢复的变化。")
        return
    print(f"{'已恢复' if done else '将要恢复'} {len(paths)} 个文件：")
    for path in paths:
        print(f"  {path}")
    print("\n" + report.get("note", ""))
    if not done:
        print("以上为预览，未写入任何文件；加 --apply 后才会恢复。")


def _diff_command(config: dict[str, Any], args: argparse.Namespace, local: Path) -> None:
    from sync_core import diff_view
    from sync_core.application import ApplicationService

    try:
        result = ApplicationService(local, template_root=ROOT).diff(choice=args.choice, apply=args.apply)
    except ValueError as error:
        raise SyncCommandError(str(error), EXIT_INCOMPLETE) from error
    diffs = result.detail["diffs"]
    status_code = {key: result.data[key] for key in ("status", "ready", "count") if key in result.data}
    if args.json:
        payload: dict[str, Any] = dict(status_code)
        if args.apply and args.choice and status_code.get("ready"):
            payload["saved"] = result.data["outcomes"]
        print(json.dumps(payload, ensure_ascii=False))
        return

    print(diff_view.render_diffs(diffs))
    if not args.choice:
        if args.apply:
            raise SyncCommandError("需要先用 --choice 指定处理方式，才能写入。", EXIT_INCOMPLETE)
        return
    for diff, outcome in zip(diffs, result.data["outcomes"]):
        if outcome.get("status") == "pending_publish":
            prefix = "已暂存，尚未共享"
        else:
            prefix = "已保存" if outcome.get("written") else "将要"
        print(f"→ {diff.tool}·{diff.label}：{diff_view.CHOICE_LABELS[args.choice]}（{prefix}）")
        print(f"    影响：{outcome['effect']}")
        if outcome.get("staged_content"):
            print(f"    待合并内容：{outcome['staged_content']}")
        if outcome.get("committed_files"):
            print(f"    提交范围：{'、'.join(outcome['committed_files'])}")
    if not args.apply:
        print("\n以上为预览，未写入任何文件；加 --apply 后才会保存。")
    elif args.choice == "share":
        print("\n已保存处理方式。")
        print("本机保存与远端发布是两步：把共享修改合并进共享模板后，")
        print("运行 sync --publish --apply 发布到配置源远端，其他设备才拿得到。")
    else:
        print("\n已保存处理方式。")


def _start_plan(config: dict[str, Any], project_id: str, report: dict[str, Any], apply: bool, state: Path) -> PlannedChanges:
    """Compatibility wrapper for the application continuation planner."""
    from sync_core.application.continuation import ContinuationError, start_plan

    try:
        return start_plan(config, project_id, report, apply=apply, state=state)
    except ContinuationError as error:
        raise SyncCommandError(str(error), error.code) from error

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=[
            "quick", "rules", "config", "memory", "doctor", "inventory", "finish", "start", "restore",
            "setup", "sync", "status", "diff", "undo", "memory-setup", "project", "scan",
            "migrate", "detach", "verify-load", "declare", "import-config",
        ],
    )
    parser.add_argument("--local", type=Path, default=None, help="device configuration (defaults to the user data directory)")
    parser.add_argument("--source", type=Path, help="import-config: old device.json path")
    parser.add_argument("--apply", action="store_true", help="Apply a previewed operation")
    parser.add_argument("--project")
    parser.add_argument("--handoff")
    parser.add_argument("--handoff-id")
    parser.add_argument("--snapshot")
    parser.add_argument("--recover", action="store_true", help="Explicitly roll back recoverable interrupted transactions")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--verbose", action="store_true", help="Show sanitized technical detail")
    parser.add_argument("--remote", help="Configuration source address recorded during setup")
    parser.add_argument("--state-dir", help="Override the local state directory during setup")
    parser.add_argument("--memory-repo", help="Override the shared memory repository path during setup")
    from sync_core.layout import default_device_config_path, default_store_path

    parser.add_argument(
        "--store",
        nargs="?",
        const=str(default_store_path()),
        default=str(default_store_path()),
        help="setup: use (or create/clone with --remote) an independent configuration store; default ~/.ai-sync/store",
    )
    parser.add_argument("--fetch", action="store_true", help="Fetch the shared configuration source before applying")
    parser.add_argument("--publish", action="store_true", help="Commit and publish this device's shared edits to the configuration source remote")
    parser.add_argument("--list", action="store_true", help="List recent operations instead of restoring")
    parser.add_argument("--operation", help="Operation id to restore")
    parser.add_argument("--index", type=int, help="1-based index of the operation to restore")
    parser.add_argument(
        "--choice",
        choices=["share", "local", "restore", "adopt", "keep", "skip", "remove"],
        help="diff: share/local/restore; migrate: adopt/keep/skip/remove",
    )
    parser.add_argument("--disable", action="store_true", help="Disable a capability while keeping local data")
    parser.add_argument("--agent", help="Agent instance id (detach, verify-load, setup)")
    parser.add_argument("--item", help="migrate: item index or id to decide on")
    parser.add_argument("--restore-original", action="store_true", help="detach: put back the rules migrate removed")
    parser.add_argument("--answer", help="verify-load: the agent's reply to the version question")
    parser.add_argument("--root", help="declare: the agent's configuration directory")
    parser.add_argument("--entry", help="declare: relative Markdown rules file a generic agent reads")
    parser.add_argument("--entry-mode", choices=["owned_file", "managed_block"], help="declare: how the generic entry is written")
    parser.add_argument("--profile", help="declare: known agent profile for a custom instance id")
    args = parser.parse_args()
    using_default_local = args.local is None
    if using_default_local:
        args.local = default_device_config_path()

    if args.mode == "import-config":
        if args.source is None:
            parser.error("import-config requires --source <old device.json>")
        from sync_core.application import ApplicationService

        report = ApplicationService(args.local, template_root=ROOT).import_config(
            source=args.source, apply=args.apply
        ).data
        if not args.apply:
            if args.json:
                print(json.dumps(report, ensure_ascii=False))
            else:
                print(f"旧配置：{report['source']}")
                print(f"新位置：{report['target']}")
                if report.get("backup"):
                    print(f"备份副本：{report['backup']}")
                print("以上为只读预览，旧文件不会删除。加 --apply 才会复制并核对。")
            return
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        elif report["status"] == "imported":
            print(f"设备配置已导入：{report['target']}")
            print(f"旧文件保留，备份副本：{report['backup']}")
        else:
            print(f"配置已在新位置：{report['target']}；没有重复写入。")
        return

    legacy_default = Path.cwd() / "device.json"
    if using_default_local and not args.local.exists() and legacy_default.is_file():
        reason = (
            f"发现旧位置的 device.json：{legacy_default}。"
            f"先运行 import-config --source \"{legacy_default}\" 预览；确认后加 --apply 导入。"
        )
        if args.json:
            print(json.dumps({"status": "needs_migration", "what": reason, "written": False}, ensure_ascii=False))
        else:
            print(reason, file=sys.stderr)
        raise SystemExit(EXIT_INCOMPLETE)

    if args.mode == "scan":
        _scan_command(args, args.local)
        return
    generated_config = args.mode in {"quick", "setup"} and not args.local.exists()
    if generated_config and args.mode == "setup":
        config = _generated_device_config(args.local)
    elif generated_config:
        config = _generated_device_config(args.local)
    else:
        config = load_config(args.local).raw
    state = config_absolute(config["state_dir"])

    if args.mode == "setup":
        _setup_command(args, args.local)
        return
    if args.mode == "sync":
        _config_sync_command(config, args, args.local)
        return
    if args.mode == "status":
        _status_command(config, args, args.local)
        return
    if args.mode == "diff":
        _diff_command(config, args, args.local)
        return
    if args.mode == "undo":
        _restore_command(config, args)
        return
    if args.mode == "memory-setup":
        _memory_setup_command(config, args, args.local)
        return
    if args.mode == "project":
        _project_command(config, args)
        return
    if args.mode == "migrate":
        _migrate_command(config, args, args.local)
        return
    if args.mode == "detach":
        _detach_command(config, args, args.local)
        return
    if args.mode == "verify-load":
        _verify_load_command(config, args, args.local)
        return
    if args.mode == "declare":
        _declare_command(config, args, args.local)
        return

    if args.mode == "quick":
        report = _quick_setup(config, args.local, apply=args.apply, generated=generated_config)
        print(json.dumps(report, ensure_ascii=False))
        return

    if args.mode in {"rules", "config", "memory"}:
        from sync_core.application import ApplicationService

        service = ApplicationService(args.local, template_root=ROOT)
        changes = service.plan(mode=args.mode) if args.local.exists() else plan(config, args.mode)
        _print_changes(changes)
        if args.apply and changes:
            result = service.apply_plan(changes, config=config)
            if result["snapshots"]:
                print("Snapshots: " + ", ".join(result["snapshots"]))
        print(f"{'Applied' if args.apply else 'Preview'}: {len(changes)} changes")
        return
    if args.mode == "inventory":
        from sync_core.application import ApplicationService

        operation = ApplicationService(args.local, template_root=ROOT).inventory(save=args.apply)
        print(json.dumps(operation.data, ensure_ascii=False))
        return
    if args.mode == "doctor":
        from sync_core.application import ApplicationService

        operation = ApplicationService(args.local, template_root=ROOT).doctor(recover=args.recover)
        report = operation.data
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            _render_doctor(report)
        if not report["ok"]:
            transport = report.get("checks", {}).get("transport", {})
            raise SystemExit(EXIT_PENDING if transport.get("status") == "pending" else EXIT_INCOMPLETE)
        return
    if args.mode == "finish":
        if not args.project or not args.handoff:
            raise ValueError("finish requires --project and --handoff")
        from sync_core.application import ApplicationService

        payload = ApplicationService(args.local, template_root=ROOT).finish(
            project_id=args.project, handoff_file=Path(args.handoff), apply=args.apply
        ).data
        print(json.dumps(payload, ensure_ascii=False))
        if args.apply and payload.get("status") == "pending":
            raise SystemExit(EXIT_PENDING)
        if args.apply and payload.get("status") == "incomplete":
            raise SystemExit(EXIT_INCOMPLETE)
        return
    if args.mode == "start":
        if not args.project or not args.handoff_id:
            raise ValueError("start requires --project and --handoff-id")
        from sync_core.application import ApplicationService
        from sync_core.application.continuation import ContinuationError

        try:
            report = ApplicationService(args.local, template_root=ROOT).start(
                project_id=args.project, handoff_id=args.handoff_id, apply=args.apply
            ).data
        except ContinuationError as error:
            raise SyncCommandError(str(error), error.code) from error
        if not report["ready"]:
            print(json.dumps(report, ensure_ascii=False))
            if args.apply:
                raise SystemExit(EXIT_INCOMPLETE)
            return
        _start_plan(config, args.project, report, args.apply, state)
        report["status"] = "ready" if args.apply else "preview"
        print(json.dumps(report, ensure_ascii=False))
        return
    if args.mode == "restore":
        if not args.snapshot:
            raise ValueError("restore requires --snapshot")
        from sync_core.application import ApplicationService

        operation = ApplicationService(args.local, template_root=ROOT).restore_snapshot(
            snapshot_id=args.snapshot, apply=args.apply
        )
        _print_changes(operation.detail)
        print(f"{'Applied' if args.apply else 'Preview'}: {operation.data['changes']} changes")


def _configure_piped_output() -> None:
    """Write UTF-8 when stdout is a pipe so the output is not locale-dependent.

    On Windows a piped Python process otherwise encodes Chinese text with the
    ANSI code page while the reader may decode UTF-8 (or the reverse).  A real
    console is left untouched: there the console API already handles Unicode, and
    an explicit ``PYTHONIOENCODING`` is always respected.
    """
    if os.environ.get("PYTHONIOENCODING"):
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            if not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


if __name__ == "__main__":
    # Output language: Chinese by default, --json for automation, --verbose for
    # sanitized technical detail.  Common failures never print a raw traceback.
    _configure_piped_output()
    _verbose = "--verbose" in sys.argv
    _json = "--json" in sys.argv
    try:
        main()
    except SyncCommandError as error:
        from sync_core import messages
        message = messages.Message(
            "E2002" if error.code == EXIT_CONFLICT else "E2001" if error.code == EXIT_PENDING else "E1001",
            str(error),
            "本机现有文件没有被删除，已写入的批次已回滚。",
            "按提示处理后重试；运行 status 可查看当前状态。",
            error.code,
            "error",
            str(error),
        )
        if _json:
            print(messages.json_error(message), file=sys.stderr)
        else:
            print(messages.render(message, verbose=_verbose), file=sys.stderr)
        raise SystemExit(error.code)
    except ConfigSyncError as error:
        # A stage-scoped failure already knows its stage and exit code; keep both
        # instead of falling through to the generic classifier below.
        from sync_core import messages
        message = messages.from_exception(error, exit_code=error.exit_code)
        if _json:
            print(messages.json_error(message), file=sys.stderr)
        else:
            print(messages.render(message, verbose=_verbose), file=sys.stderr)
        raise SystemExit(error.exit_code)
    except OwnershipError as error:
        # A refused ownership choice is a user-actionable conflict, not an
        # unclassified error: keep the code the raiser chose.
        from sync_core import messages
        code = error.exit_code or EXIT_CONFLICT
        message = messages.Message(
            "E4002",
            str(error),
            "没有写入任何文件；本机现有内容保持不变。",
            "按提示重新选择处理方式（share / restore），再运行 diff 或 sync。",
            code,
            "conflict",
            str(error),
        )
        if _json:
            print(messages.json_error(message), file=sys.stderr)
        else:
            print(messages.render(message, verbose=_verbose), file=sys.stderr)
        raise SystemExit(code)
    except (ValueError, OSError, RuntimeError) as error:
        from sync_core import messages
        message_text = str(error)
        lowered = message_text.casefold()
        if "conflict" in lowered or "collision" in lowered:
            code = EXIT_CONFLICT
        elif any(token in lowered for token in ("pending", "network", "remote", "push")):
            code = EXIT_PENDING
        elif any(token in lowered for token in ("missing", "not found", "not ready", "cannot continue", "invalid")):
            code = EXIT_INCOMPLETE
        else:
            code = 1
        message = messages.from_exception(error, exit_code=code)
        if _json:
            print(messages.json_error(message), file=sys.stderr)
        else:
            print(messages.render(message, verbose=_verbose), file=sys.stderr)
        raise SystemExit(code)
