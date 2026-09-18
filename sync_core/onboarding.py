"""Optional memory onboarding and project continuation entry points.

Memory is an opt-in capability that is offered *after* configuration
synchronization works.  Nothing here checks a memory remote or blocks
configuration sync while memory is disabled.

Capabilities are stated honestly:

* a Claude native memory directory can be synchronized in both directions
* a Codex source stays a reference snapshot and is never imported back into the
  native Codex memory database
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Callable, Mapping

from .inventory import discover

#: How each tool's source actually behaves.  Shown to the user verbatim.
SOURCE_CAPABILITY = {
    "claude": "双向同步：本机目录与共享仓库互相更新，其他设备可读取。",
    "codex": "参考快照：只导出快照作为跨设备参考，不会回填 Codex 原生记忆数据库。",
    "unknown": "未确认能力：需要先确认映射后再启用。",
}

#: Source statuses that are visible but cannot be enabled yet.
BLOCKING_STATUSES = {"missing", "unreadable", "blocked_secret", "unsupported", "path_collision"}
PENDING_STATUSES = {"pending_mapping"}

#: Placeholder rows `discover()` emits when a tool root is absent.  They record
#: the absence, they are not memory sources the user could enable, and showing
#: them as sources would make "no memory source" impossible to express.
PLACEHOLDER_STATUSES = {"not_configured", "not_enabled"}

#: Claude stores one conversation-memory directory per project under
#: ``<root>/projects/<name>/memory``.  The trailing segment is a layout
#: convention, so it must never be used as the project id.
MEMORY_DIR_NAME = "memory"


class MemorySetupError(RuntimeError):
    """Memory onboarding cannot continue; configuration is unaffected."""


def candidate_sources(config: Mapping[str, Any], *, project_root: Path | None = None) -> list[dict[str, Any]]:
    """List real memory sources with their state, including ones needing mapping.

    Absence placeholders (``not_configured`` / ``not_enabled``) are dropped, so
    an empty list honestly means "this device can run configuration sync on its
    own and never has to touch memory".
    """
    from .config import DeviceConfig

    if isinstance(config, DeviceConfig):
        device = config
    else:
        device = DeviceConfig(dict(config), None)
    inventory = discover(device)
    rows: list[dict[str, Any]] = []
    for source in inventory["sources"]:
        if source["tool"] not in {"claude", "codex"}:
            continue
        status = source["status"]
        if status in PLACEHOLDER_STATUSES:
            continue
        project_id = source.get("project_id") or _derive_id(source.get("path") or "")
        rows.append({
            "source_id": source["source_id"],
            "tool": source["tool"],
            "status": status,
            "path": source["path"],
            "project_id": project_id,
            "suggested_id": project_id,
            "file_count": source["file_count"],
            "capability": SOURCE_CAPABILITY.get(source["tool"], SOURCE_CAPABILITY["unknown"]),
            "enableable": status not in BLOCKING_STATUSES,
            "needs_mapping": status in PENDING_STATUSES,
            "reason": source.get("detail"),
        })
    return rows


def describe_sources(rows: list[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for row in rows:
        marker = "可启用" if row["enableable"] else "暂不可启用"
        pending = "，待映射" if row["needs_mapping"] else ""
        lines.append(f"{row['source_id']}（{row['tool']}）：{marker}{pending}，{row['file_count']} 个文件")
        if row.get("suggested_id"):
            lines.append(f"    建议项目标识：{row['suggested_id']}（可修改）")
        lines.append(f"    能力：{row['capability']}")
        if row["reason"]:
            lines.append(f"    说明：{row['reason']}")
    if not rows:
        lines.append("未发现可用的记忆来源；可以先只使用配置同步。")
    return lines


def plan_memory_enable(
    *,
    config: Mapping[str, Any],
    selections: list[Mapping[str, Any]],
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Turn confirmed sources into memory mappings, without editing JSON by hand."""
    mappings: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    for selection in selections:
        project_id = str(selection.get("id", "")).strip()
        path = str(selection.get("path", "")).strip()
        if not project_id:
            # A new project may be appended later; derive a portable id from the
            # directory name so the user never has to invent one.
            project_id = _derive_id(path)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project_id):
            rejected.append({"path": path, "reason": f"无法生成合法的项目标识：{project_id}"})
            continue
        if project_id in seen:
            rejected.append({"path": path, "reason": f"项目标识重复：{project_id}"})
            continue
        if not path:
            rejected.append({"path": path, "reason": "缺少本机路径"})
            continue
        seen.add(project_id)
        entry: dict[str, Any] = {"id": project_id, "path": path}
        if selection.get("exclude"):
            entry["exclude"] = list(selection["exclude"])
        if selection.get("initialize"):
            entry["initialize"] = True
        mappings.append(entry)
    return {
        "status": "ready" if mappings else "empty",
        "mappings": mappings,
        "rejected": rejected,
        "note": "保存后记忆同步才会启用；未启用记忆不影响配置同步。",
    }


def _derive_id(path: str) -> str:
    """Derive a portable project id from a path without asking the user.

    A Claude memory source always ends in ``<project>/memory``; the project
    directory is the meaningful name, so the convention segment is skipped.
    """
    normalized = str(path).replace("\\", "/").rstrip("/")
    if not normalized:
        return ""
    segments = [segment for segment in normalized.split("/") if segment]
    if len(segments) > 1 and segments[-1].casefold() == MEMORY_DIR_NAME:
        segments = segments[:-1]
    if not segments:
        return ""
    name = segments[-1]
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.casefold()).strip("-")
    return slug[:48].rstrip("-")


def disable_memory(config: Mapping[str, Any]) -> dict[str, Any]:
    """Disable memory while keeping the original data untouched."""
    return {
        "status": "disabled",
        "removed_mappings": [item.get("id") for item in config.get("memories", [])],
        "note": "已保留本机原始记忆文件；只是不再同步，未删除任何内容。",
    }


# --------------------------------------------------------------------------
# TASK-16: project continuation entry point
# --------------------------------------------------------------------------

def recent_handoffs(memory_repo: Path, project_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """List the most recent usable handoffs for a project, newest first."""
    import json

    directory = memory_repo / "handoffs" / project_id
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows.append({
            "handoff_id": data.get("handoff_id") or path.stem,
            "created_at": data.get("created_at"),
            "status": data.get("status"),
            "memory_snapshot": data.get("memory_snapshot"),
            "missing_fields": data.get("missing_fields", []),
        })
    rows.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return rows[:limit]


def list_projects(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Projects the user can pick from, without typing an internal id."""
    projects = config.get("projects", {}) or {}
    memories = {item.get("id"): item for item in config.get("memories", [])}
    rows: list[dict[str, Any]] = []
    for project_id, path in sorted(projects.items()):
        mapping = memories.get(project_id)
        rows.append({
            "project_id": project_id,
            "path": path,
            "name": Path(str(path)).name,
            "has_memory": mapping is not None,
        })
    return rows


def continuation_report(
    config: Mapping[str, Any],
    memory_repo: Path,
    *,
    project_id: str,
    handoff_id: str | None = None,
    inspector: Callable[[str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize a handoff so the user can confirm before continuing."""
    import json

    rows = recent_handoffs(memory_repo, project_id)
    if not rows:
        return {
            "status": "unavailable",
            "ready": False,
            "reason": "该项目还没有可用于接续的交接记录。",
        }
    chosen = None
    if handoff_id:
        chosen = next((row for row in rows if row["handoff_id"] == handoff_id), None)
        if chosen is None:
            return {"status": "unavailable", "ready": False, "reason": f"未找到交接记录：{handoff_id}"}
    else:
        chosen = rows[0]

    document = memory_repo / "handoffs" / project_id / f"{chosen['handoff_id']}.md"
    sections: dict[str, str] = {}
    if document.exists():
        sections = _sections(document.read_text(encoding="utf-8"))
    checks: dict[str, Any] = {
        "handoff_complete": chosen.get("status") in {"ready", "uploaded"},
        "has_document": document.exists(),
        "has_snapshot": bool(chosen.get("memory_snapshot")),
    }
    if inspector is not None:
        try:
            checks["inspection"] = dict(inspector(chosen["handoff_id"]))
        except Exception as error:  # noqa: BLE001 - report instead of crashing
            checks["inspection"] = {"ready": False, "error": str(error)}
    ready = all(bool(value) for key, value in checks.items() if key != "inspection") and bool(
        checks.get("inspection", {}).get("ready", True)
    )
    return {
        "status": "ready" if ready else "incomplete",
        "ready": ready,
        "project_id": project_id,
        "handoff_id": chosen["handoff_id"],
        "created_at": chosen.get("created_at"),
        "available_handoffs": rows,
        "goal": sections.get("goal"),
        "completed": sections.get("completed"),
        "next_step": sections.get("next_step"),
        "remaining": sections.get("remaining"),
        "version": chosen.get("memory_snapshot"),
        "unsynced": chosen.get("missing_fields", []),
        "checks": checks,
        "note": "历史交接与当前交接分开列出；缺少资料时不会显示为可以完整接续。",
    }


def _sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    aliases = {
        "goal": "goal", "目標": "goal", "user goal": "goal",
        "completed": "completed", "已完成": "completed",
        "remaining": "remaining", "尚未完成": "remaining", "待辦": "remaining",
        "next": "next_step", "下一步": "next_step",
    }
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            heading = line.lstrip("#").strip().casefold()
            current = next((value for key, value in aliases.items() if key in heading), None)
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    return sections
