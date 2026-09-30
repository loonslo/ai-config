"""User-level restore: undo the last configuration apply by operation.

The user picks a recent operation by time, tool and change count; there is no
need to find a UUID or backup number.  Before restoring, both the backup and
any later change to the target are checked.

Configuration restore stays separate from memory snapshot restore, and a restore
never becomes the new shared value automatically.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .transaction import PlannedChanges, SyncLock, transaction, write_file
from .utils import atomic_write, digest, json_bytes, read_bytes


class RestoreError(RuntimeError):
    """The restore cannot proceed safely."""


def _journals(state_dir: Path) -> list[dict[str, Any]]:
    root = state_dir / "transactions"
    if not root.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in root.glob("*.json"):
        try:
            journal = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        journal["journal_path"] = str(path)
        records.append(journal)
    records.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return records


#: Operations a user can undo: configuration applies, migrations, detaches and
#: agent declarations.
UNDOABLE_OPERATIONS = ("config", "migrate", "detach", "declare")


def recent_operations(
    state_dir: Path,
    *,
    limit: int = 10,
    operation_filter: str | tuple[str, ...] | None = UNDOABLE_OPERATIONS,
) -> list[dict[str, Any]]:
    """List recent applies as time, tool and change count — no UUID required."""
    allowed = (operation_filter,) if isinstance(operation_filter, str) else operation_filter
    listing: list[dict[str, Any]] = []
    for journal in _journals(state_dir):
        if journal.get("status") != "COMMITTED":
            continue
        operation = (journal.get("metadata") or {}).get("operation", "")
        if allowed and operation and operation not in allowed:
            continue
        changes = journal.get("changes", [])
        path_agents = (journal.get("metadata") or {}).get("path_agents") or {}
        tools = sorted({path_agents.get(str(item.get("path", ""))) or _tool_for(str(item.get("path", ""))) for item in changes} - {None})
        listing.append({
            "operation_id": journal.get("operation_id"),
            "operation": operation,
            "created_at": journal.get("created_at"),
            "change_count": len(changes),
            "tools": tools,
            "backup": journal.get("backup"),
            "changes": changes,
            "journal_path": journal.get("journal_path"),
            "statement": _statement(journal, tools, len(changes)),
        })
        if len(listing) >= limit:
            break
    return listing


def _tool_for(path: str) -> str | None:
    lowered = path.casefold()
    if "agents.md" in lowered or "config.toml" in lowered:
        return "codex"
    if "claude.md" in lowered or "settings.json" in lowered:
        return "claude"
    return None


def _statement(journal: Mapping[str, Any], tools: list[str], count: int) -> str:
    when = str(journal.get("created_at", ""))[:19].replace("T", " ")
    tool_text = "、".join(tools) if tools else "配置"
    verb = {"migrate": "迁入", "detach": "退出接管", "declare": "登记"}.get(str((journal.get("metadata") or {}).get("operation")), "应用")
    return f"{when} 对 {tool_text} {verb}了 {count} 处更改"


def select_operation(state_dir: Path, *, operation_id: str | None = None, index: int | None = None) -> dict[str, Any]:
    """Resolve a user selection to exactly one operation.

    ``index`` is the 1-based position in the listing shown to the user.
    """
    operations = recent_operations(state_dir)
    if not operations:
        raise RestoreError("没有可恢复的配置应用记录。")
    if operation_id:
        for item in operations:
            if item["operation_id"] == operation_id:
                return item
        raise RestoreError(f"未找到指定的应用记录：{operation_id}")
    if index is None:
        raise RestoreError("请选择要撤销的应用记录（序号或 ID）。")
    if index < 1 or index > len(operations):
        raise RestoreError(f"序号超出范围：{index}（共 {len(operations)} 条）")
    return operations[index - 1]


def plan_restore(state_dir: Path, operation: Mapping[str, Any]) -> PlannedChanges:
    """Build the restore batch, verifying the backup and later target edits."""
    backup = Path(str(operation["backup"]))
    manifest_path = backup / "manifest.json"
    if not manifest_path.exists():
        raise RestoreError("备份清单缺失，无法安全恢复。")
    try:
        records = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RestoreError("备份清单已损坏，无法安全恢复。") from error

    # ``wrote`` maps a path to the digest of the content this operation wrote, so
    # a later edit can be told apart from the version we are expecting.
    wrote = {str(item.get("path")): item.get("sha256") for item in operation.get("changes", [])}

    changes: dict[Path, bytes | None] = {}
    expected: dict[Path, str | None] = {}
    conflicts: list[str] = []
    for record in records:
        target = Path(record["path"])
        stored = None
        if record.get("existed"):
            stored_path = backup / str(record["file"])
            if not stored_path.exists():
                raise RestoreError(f"备份内容缺失，无法安全恢复：{target}")
            stored = stored_path.read_bytes()
            if digest(stored) != record.get("sha256"):
                raise RestoreError(f"备份内容与清单哈希不符，拒绝恢复：{target}")
        current = read_bytes(target)
        current_hash = digest(current)
        # The target may hold either the version we wrote or the version the
        # backup captured. Anything else is a later user edit and is surfaced
        # rather than silently overwritten.
        if str(target) in wrote:
            acceptable = {wrote[str(target)], record.get("sha256")}
        else:
            acceptable = {record.get("sha256")}
        if current_hash not in acceptable:
            conflicts.append(str(target))
            continue
        if current != stored:
            changes[target] = stored
        expected[target] = current_hash
    if conflicts:
        raise RestoreError(
            "以下文件在应用之后又被修改，恢复会覆盖这些改动，请先确认："
            + "、".join(conflicts)
        )
    return PlannedChanges(
        changes,
        expected=expected,
        state_root=state_dir,
        metadata={"operation": "config", "restored_operation": operation.get("operation_id")},
    )


def restore(
    state_dir: Path,
    *,
    operation_id: str | None = None,
    index: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Restore the managed fields to the selected operation's prior state."""
    operation = select_operation(state_dir, operation_id=operation_id, index=index)
    if operation.get("operation") not in UNDOABLE_OPERATIONS:
        raise RestoreError("该记录不是配置应用、迁入或退出接管，不能用配置恢复处理。")
    plan = plan_restore(state_dir, operation)
    result = {
        "status": "preview",
        "ready": False,
        "operation": operation,
        "changes": len(plan),
        "paths": sorted(str(path) for path in plan),
        "note": "预览不会写入文件。恢复本机配置不会把它推送为共享最新值。",
    }
    if not apply or not plan:
        return result
    try:
        with SyncLock(state_dir):
            transaction(plan, state_dir / "backups", state_root=state_dir, lock=False)
    except Exception as error:  # noqa: BLE001 - single user-facing boundary
        raise RestoreError(f"恢复失败，文件已回滚到恢复前状态：{error}") from error
    result["status"] = "restored"
    result["ready"] = True
    result["note"] = "本机受管字段已恢复到当时的值；该状态不会自动成为共享最新值。"
    return result
