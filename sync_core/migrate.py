"""Migrate existing agent rules into the store, and take an agent back out.

``migrate`` works on Markdown sections of the rules a user already has in each
agent (outside any ai-config managed block):

* a section whose every meaningful line is already in the store is a
  **duplicate**; the default is to remove it from the agent file (after a
  backup), so the agent does not read the same rule twice;
* a section with lines the store does not have is **unique**; nothing happens
  to it until the user chooses ``adopt`` (append those lines, verbatim and with
  their source, to ``common/imported.md`` and remove the section), ``keep``
  (leave it where it is and stop asking) or ``remove``;
* an agent found on the host but not yet managed can be **registered** in
  device.json.

Comparison is deterministic (``sync_core.rules_text``); no model rewrites
anything.  Every write goes through the recoverable transaction, so ``undo``
reverts a migration, and the first original of every file migrate changes is
kept so ``detach --restore-original`` can put it back.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from . import agents, rules_text
from .agents import AgentInstance, HostEnv
from .rules_text import Line
from .scan import _existing_rule_files, _instance_for, _read_rules_file, display_path
from .transaction import PlannedChanges
from .utils import atomic_write, digest, json_bytes

MIGRATE_CHOICES = ("adopt", "keep", "skip", "remove")
KIND_REGISTER = "register"
KIND_DUPLICATE = "duplicate"
KIND_UNIQUE = "unique"

ALLOWED_CHOICES = {
    KIND_REGISTER: ("adopt", "skip"),
    KIND_DUPLICATE: ("remove", "keep", "skip"),
    KIND_UNIQUE: ("adopt", "keep", "remove", "skip"),
}

CHOICE_LABELS = {
    "adopt": "采纳到配置库",
    "keep": "保留在原处，不再提示",
    "skip": "暂不处理",
    "remove": "从原文件移除（先备份）",
}

IMPORTED_TOPIC = "imported"
IMPORTED_HEADER = (
    "# 迁入的规则\n"
    "\n"
    "以下内容由 ai-config migrate 从各 agent 原有规则中迁入，保留原文与来源；"
    "整理到其他主题文件后，可以删除这里对应的段落。\n"
)

_HEADING = re.compile(r"^ {0,3}#{1,6}\s")


class MigrationError(RuntimeError):
    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------

def _pieces(text: str) -> list[str]:
    """Split into lines that keep their own line ending."""
    return [piece for piece in re.split(r"(?<=\n)", text) if piece]


@dataclass(frozen=True)
class Section:
    start: int
    end: int
    heading: str | None
    raw: str
    lines: tuple[Line, ...]


def split_sections(text: str, *, first_line: int = 1) -> list[Section]:
    """Markdown sections of ``text``; blank lines belong to the section above."""
    sections: list[Section] = []
    current: list[str] = []
    start = first_line

    def close(end: int) -> None:
        if not current:
            return
        raw = "".join(current)
        heading = rules_text.normalize(current[0]) if _HEADING.match(current[0]) else None
        sections.append(Section(start, end, heading, raw, tuple(rules_text.meaningful_lines(raw, start=start))))

    number = first_line
    for piece in _pieces(text):
        if _HEADING.match(piece) and current:
            close(number - 1)
            current, start = [], number
        current.append(piece)
        number += 1
    close(number - 1)
    return sections


def strip_block(data: bytes) -> bytes | None:
    """The file without the ai-config block, undoing the separator sync added.

    ``None`` means nothing of the user's is left, so the file can go.
    """
    outside = rules_text.outside_block(data)
    if not outside.has_block:
        return data
    before, after = outside.before, outside.after
    if after in {"", "\n", "\r\n"} and before.endswith("\n\n"):
        # sync appended "\n\n" + block + "\n" to an existing file.
        before, after = before[:-2], ""
    text = before + after
    return None if not text.strip() else text.encode("utf-8")


# --------------------------------------------------------------------------
# planning
# --------------------------------------------------------------------------

@dataclass
class Item:
    id: str
    kind: str
    instance: str
    name: str
    default: str | None
    relative: str | None = None
    path: Path | None = None
    root: Path | None = None
    section: Section | None = None
    known: int = 0
    unique: tuple[Line, ...] = ()
    shared_with: tuple[str, ...] = ()

    @property
    def choices(self) -> tuple[str, ...]:
        return ALLOWED_CHOICES[self.kind]


@dataclass
class MigrationPlan:
    items: list[Item]
    blocked: list[dict[str, Any]]
    store_root: Path
    raw: dict[str, Any]
    local: Path
    host: HostEnv
    decided: dict[str, Any] = field(default_factory=dict)


def _short(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def _decisions_path(state_dir: Path) -> Path:
    return state_dir / "migration" / "decisions.json"


def _originals_path(state_dir: Path) -> Path:
    return state_dir / "migration" / "originals.json"


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise MigrationError(f"迁移记录无法读取，请检查后重试：{path}")
    return data if isinstance(data, dict) else dict(default)


def _candidates(raw: Mapping[str, Any], host: HostEnv) -> tuple[list[AgentInstance], list[AgentInstance]]:
    """Registered instances, and writable instances found but not registered."""
    registered = agents.agent_instances(raw)
    known = {instance.id for instance in registered}
    found = [
        _instance_for(item)
        for item in agents.detect_instances(host)
        if item.profile.writable and item.exists and item.instance not in known
    ]
    return registered, found


def _rule_sources(instance: AgentInstance) -> list[tuple[Path, str]]:
    """Files holding hand-written rules for an instance (never ai-config's own file)."""
    if not instance.root.is_dir():
        return []
    entry = agents.rules_target(instance) if agents.unresolved_reason(instance) is None else None
    sources: list[tuple[Path, str]] = []
    if entry is not None and entry.mode == agents.MODE_BLOCK and entry.path.is_file():
        sources.append((entry.path, entry.path.relative_to(instance.root).as_posix()))
    sources.extend(_existing_rule_files(instance.root, instance.profile, entry.path if entry else None))
    unique: dict[Path, str] = {}
    for path, relative in sources:
        unique.setdefault(path, relative)
    return sorted(unique.items(), key=lambda item: item[1])


def plan_migration(raw: Mapping[str, Any], *, local: Path, host: HostEnv, store_root: Path, state_dir: Path) -> MigrationPlan:
    known_keys = rules_text.store_keys(store_root)
    decisions = _load_json(_decisions_path(state_dir), {"schema_version": 1, "items": {}})
    decided: dict[str, Any] = dict(decisions.get("items", {}))
    registered, found = _candidates(raw, host)
    items: list[Item] = []
    blocked: list[dict[str, Any]] = []

    for instance in found:
        item_id = _short(f"register:{instance.id}")
        if decided.get(item_id, {}).get("choice") == "skip":
            continue
        items.append(Item(item_id, KIND_REGISTER, instance.id, agents.display_name(instance.id), "adopt", root=instance.root))

    sections_by_instance: list[tuple[AgentInstance, Path, str, Section]] = []
    for instance in [*registered, *found]:
        for path, relative in _rule_sources(instance):
            data, problem = _read_rules_file(path)
            if problem is not None:
                blocked.append({"instance": instance.id, "path": relative, "reason": problem})
                continue
            outside = rules_text.outside_block(data)
            if outside.block_error is not None:
                blocked.append({"instance": instance.id, "path": relative, "reason": "malformed_block"})
                continue
            parts = split_sections(outside.before) + split_sections(outside.after, first_line=outside.after_start)
            for section in parts:
                if section.lines:
                    sections_by_instance.append((instance, path, relative, section))

    # Which instances hold each unknown line, so a rule copied into several
    # agents is recognized as one rule.
    holders: dict[str, set[str]] = {}
    for instance, _, _, section in sections_by_instance:
        for line in section.lines:
            if line.key not in known_keys:
                holders.setdefault(line.key, set()).add(instance.id)

    for instance, path, relative, section in sections_by_instance:
        comparison = rules_text.compare(section.lines, known_keys)
        item_id = _short(f"section:{instance.id}:{relative}:{digest(rules_text.normalize(section.raw).encode('utf-8'))}")
        if decided.get(item_id, {}).get("choice") == "keep":
            continue
        shared = sorted({other for line in comparison.unique for other in holders.get(line.key, ()) if other != instance.id})
        kind = KIND_DUPLICATE if not comparison.unique else KIND_UNIQUE
        items.append(Item(
            item_id,
            kind,
            instance.id,
            agents.display_name(instance.id),
            "remove" if kind == KIND_DUPLICATE else None,
            relative=relative,
            path=path,
            root=instance.root,
            section=section,
            known=len(comparison.known),
            unique=comparison.unique,
            shared_with=tuple(shared),
        ))
    return MigrationPlan(items, blocked, store_root, dict(raw), local, host, decided)


def select(plan: MigrationPlan, *, item: str | None, choice: str | None) -> dict[str, str]:
    """Resolve the user's selection into ``{item_id: choice}``.

    Without ``item`` only the safe defaults run (register, remove duplicates);
    unique content is never touched without an explicit choice.
    """
    if item is None:
        if choice is not None:
            raise MigrationError("--choice 需要和 --item 一起使用，指明处理哪一项。", exit_code=2)
        return {entry.id: entry.default for entry in plan.items if entry.default}
    match = None
    if item.isdigit() and 1 <= int(item) <= len(plan.items):
        match = plan.items[int(item) - 1]
    else:
        match = next((entry for entry in plan.items if entry.id == item), None)
    if match is None:
        raise MigrationError(f"没有找到迁入项：{item}；先运行 migrate 查看当前列表。", exit_code=2)
    if choice is None:
        raise MigrationError("请用 --choice 指定处理方式：" + "、".join(match.choices), exit_code=2)
    if choice not in match.choices:
        raise MigrationError(f"这一项不能选择 {choice}；可选：" + "、".join(match.choices), exit_code=4)
    return {match.id: choice}


# --------------------------------------------------------------------------
# building the write batch
# --------------------------------------------------------------------------

def _rebuild(data: bytes, remove: Iterable[Section]) -> bytes | None:
    """The file with the given sections removed; ``None`` when nothing remains."""
    removed = {(section.start, section.end) for section in remove}
    outside = rules_text.outside_block(data)

    def keep(text: str, first_line: int) -> str:
        return "".join(section.raw for section in split_sections(text, first_line=first_line) if (section.start, section.end) not in removed)

    before = keep(outside.before, 1)
    after = keep(outside.after, outside.after_start)
    if not outside.has_block:
        text = before + after
        return None if not text.strip() else text.encode("utf-8")
    block, _ = rules_text.managed_block(data)
    if not before.strip():
        before = ""
    if not after.strip():
        after = "\n"
    return before.encode("utf-8") + block + after.encode("utf-8")


def _adopted_text(entries: list[Item], existing_keys: set[str]) -> str:
    date = datetime.now(timezone.utc).date().isoformat()
    chunks: list[str] = []
    seen = set(existing_keys)
    for entry in entries:
        lines = [line for line in entry.unique if line.key not in seen]
        if not lines:
            continue
        seen.update(line.key for line in lines)
        raw_lines = rules_text.split_lines(entry.section.raw) if entry.section else []
        heading = raw_lines[0].rstrip() if entry.section and entry.section.heading else None
        body = [raw_lines[line.number - entry.section.start].rstrip() for line in lines] if entry.section else []
        header = f"## 迁入：{entry.name} · {entry.relative}（第 {entry.section.start}–{entry.section.end} 行，{date}）"
        chunk = [header, ""]
        if heading and rules_text.key(heading) not in {line.key for line in lines}:
            chunk.append(heading)
        chunk.extend(body)
        chunks.append("\n".join(chunk))
    return "\n\n".join(chunks)


def build_changes(plan: MigrationPlan, selections: Mapping[str, str], *, state_dir: Path) -> tuple[PlannedChanges, dict[str, Any]]:
    """Every file write the selections imply, as one recoverable batch."""
    from .config import validate
    from .utils import read_bytes

    by_id = {item.id: item for item in plan.items}
    chosen = [(by_id[item_id], choice) for item_id, choice in selections.items() if item_id in by_id]
    changes: dict[Path, bytes | None] = {}
    expected: dict[Path, str | None] = {}
    path_agents: dict[str, str] = {}
    summary: dict[str, list[str]] = {"registered": [], "removed": [], "adopted": [], "kept": [], "skipped": []}

    # 1. sections leaving agent files (remove and adopt)
    removals: dict[Path, list[Item]] = {}
    adopted: list[Item] = []
    for item, choice in chosen:
        if item.kind == KIND_REGISTER:
            continue
        if choice in {"remove", "adopt"}:
            removals.setdefault(item.path, []).append(item)
        if choice == "adopt":
            adopted.append(item)
    originals = _load_json(_originals_path(state_dir), {"schema_version": 1, "files": {}})
    files = originals.setdefault("files", {})
    for path, entries in sorted(removals.items(), key=lambda pair: str(pair[0])):
        current = read_bytes(path)
        if current is None:
            raise MigrationError(f"文件在预览之后被删除，请重新运行 migrate：{path}")
        rebuilt = _rebuild(current, [entry.section for entry in entries if entry.section])
        changes[path] = rebuilt
        expected[path] = digest(current)
        entry = entries[0]
        path_agents[str(path)] = entry.instance
        record_key = f"{entry.instance}:{entry.relative}"
        if record_key not in files:
            blob = state_dir / "migration" / "originals" / f"{digest(current)}.bin"
            if not blob.exists():
                changes[blob] = current
                expected[blob] = None
            files[record_key] = {"sha256": digest(current), "blob": blob.name, "root": str(entry.root), "relative": entry.relative}
        files[record_key]["after_outside"] = digest(strip_block(rebuilt) if rebuilt is not None else None)
        files[record_key]["migrated_at"] = _now()
        for item in entries:
            summary["adopted" if item in adopted else "removed"].append(item.id)

    # 2. adopted lines join the store, verbatim and with their source
    if adopted:
        target = plan.store_root / "common" / f"{IMPORTED_TOPIC}.md"
        current = read_bytes(target)
        existing_keys = rules_text.store_keys(plan.store_root)
        addition = _adopted_text(adopted, existing_keys)
        if addition:
            base = current.decode("utf-8") if current is not None else IMPORTED_HEADER
            text = base.rstrip("\n") + "\n\n" + addition + "\n"
            changes[target] = text.encode("utf-8")
            expected[target] = digest(current)

    # 3. registration and remembered decisions
    raw = json.loads(json.dumps(plan.raw))
    registered_now = False
    decisions = _load_json(_decisions_path(state_dir), {"schema_version": 1, "items": {}})
    decisions.setdefault("items", {})
    for item, choice in chosen:
        if item.kind == KIND_REGISTER:
            if choice == "adopt":
                if item.instance in agents.LEGACY_INSTANCES:
                    raw[item.instance] = str(item.root)
                else:
                    raw.setdefault("agents", {})[item.instance] = {"root": str(item.root)}
                registered_now = True
                summary["registered"].append(item.id)
            else:
                decisions["items"][item.id] = {"choice": "skip", "instance": item.instance, "decided_at": _now()}
                summary["skipped"].append(item.id)
        elif choice == "keep":
            decisions["items"][item.id] = {"choice": "keep", "instance": item.instance, "path": item.relative, "decided_at": _now()}
            summary["kept"].append(item.id)
    if registered_now:
        validate(raw)
        current = read_bytes(plan.local)
        changes[plan.local] = json_bytes(raw)
        expected[plan.local] = digest(current)
    if summary["kept"] or summary["skipped"]:
        path = _decisions_path(state_dir)
        current = read_bytes(path)
        changes[path] = json_bytes(decisions)
        expected[path] = digest(current)
    if removals:
        path = _originals_path(state_dir)
        current = read_bytes(path)
        changes[path] = json_bytes(originals)
        expected[path] = digest(current)
    plan_changes = PlannedChanges(
        changes,
        expected=expected,
        state_root=state_dir,
        metadata={"operation": "migrate", "path_agents": path_agents},
    )
    return plan_changes, summary


# --------------------------------------------------------------------------
# detach
# --------------------------------------------------------------------------

def plan_detach(raw: Mapping[str, Any], *, local: Path, instance_id: str, state_dir: Path, restore_original: bool) -> tuple[PlannedChanges, dict[str, Any]]:
    """Remove what ai-config wrote for one agent and unregister it."""
    from .utils import read_bytes

    instance = next((item for item in agents.agent_instances(raw) if item.id == instance_id), None)
    if instance is None:
        raise MigrationError(f"本机没有登记这个 agent：{instance_id}；运行 status 或 scan 查看已登记的 agent。")
    changes: dict[Path, bytes | None] = {}
    expected: dict[Path, str | None] = {}
    report: dict[str, Any] = {"instance": instance_id, "name": agents.display_name(instance_id), "files": [], "conflicts": [], "restored": []}
    entry = agents.rules_target(instance) if agents.unresolved_reason(instance) is None else None
    if entry is not None and entry.path.is_file():
        current = read_bytes(entry.path)
        result = strip_block(current)
        if result != current:
            changes[entry.path] = result
            expected[entry.path] = digest(current)
            report["files"].append({"path": str(entry.path), "action": "delete" if result is None else "remove_block"})
    report["remove_empty_dir"] = (
        str(entry.path.parent)
        if entry is not None and instance.rules is not None and instance.rules.mode == agents.MODE_FILE and "/" in instance.rules.path
        else None
    )

    originals = _load_json(_originals_path(state_dir), {"schema_version": 1, "files": {}})
    files = originals.setdefault("files", {})
    if restore_original:
        for key, record in sorted(files.items()):
            if not key.startswith(f"{instance_id}:"):
                continue
            target = Path(record["root"]) / record["relative"]
            now = changes[target] if target in changes else read_bytes(target)
            if digest(strip_block(now) if now is not None else None) != record.get("after_outside"):
                report["conflicts"].append({"path": str(target), "reason": "迁入后该文件又被修改，未恢复原件，以免覆盖新内容"})
                continue
            blob = state_dir / "migration" / "originals" / record["blob"]
            original = read_bytes(blob)
            if original is None or digest(original) != record["sha256"]:
                report["conflicts"].append({"path": str(target), "reason": "原件备份缺失或哈希不符，未恢复"})
                continue
            restored = strip_block(original)
            if target not in expected:
                expected[target] = digest(read_bytes(target))
            changes[target] = restored
            report["restored"].append(str(target))
            del files[key]
        if report["restored"]:
            path = _originals_path(state_dir)
            changes[path] = json_bytes(originals)
            expected[path] = digest(read_bytes(path))

    updated = json.loads(json.dumps(dict(raw)))
    if instance.legacy:
        updated.pop(instance_id, None)
    else:
        declared = updated.get("agents") or {}
        declared.pop(instance_id, None)
        if declared:
            updated["agents"] = declared
        else:
            updated.pop("agents", None)
    changes[local] = json_bytes(updated)
    expected[local] = digest(read_bytes(local))
    for marker in (state_dir / f"{instance_id}-rules.json", state_dir / f"{instance_id}-rules-accept-shared.json"):
        if marker.exists():
            changes[marker] = None
            expected[marker] = digest(read_bytes(marker))
    path_agents = {str(path): instance_id for path in changes if path != local}
    return PlannedChanges(changes, expected=expected, state_root=state_dir, metadata={"operation": "detach", "path_agents": path_agents}), report


def remove_empty_dir(path: str | None) -> bool:
    """Remove a directory ai-config created for an owned file, if now empty."""
    if not path:
        return False
    directory = Path(path)
    try:
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
            return True
    except OSError:
        return False
    return False


# --------------------------------------------------------------------------
# Chinese rendering
# --------------------------------------------------------------------------

_KIND_LABEL = {KIND_REGISTER: "登记接管对象", KIND_DUPLICATE: "完全重复", KIND_UNIQUE: "含独有内容"}
_BLOCK_REASON = {
    "blocked_secret": "疑似包含凭据，已跳过（未输出内容）",
    "malformed_block": "受管区块标记损坏，需要人工检查",
    "not_utf8": "不是 UTF-8 文本，已跳过",
    "unreadable": "无法读取",
    "symlink": "是符号链接，不跟随",
}


def render_plan(plan: MigrationPlan) -> str:
    lines = [f"迁入预览（配置库：{display_path(plan.store_root, plan.host)}）", ""]
    if not plan.items and not plan.blocked:
        lines.append("没有需要迁入或登记的内容。")
        return "\n".join(lines)
    for position, item in enumerate(plan.items, start=1):
        prefix = f"  [{position}] {item.id}"
        if item.kind == KIND_REGISTER:
            lines.append(f"{prefix} 登记 {agents.label(item.instance)}  {display_path(item.root, plan.host)}  → 默认：登记")
            continue
        section = item.section
        title = f"「{section.heading}」" if section and section.heading else "（无标题段落）"
        where = f"{agents.label(item.instance)} {item.relative} 第 {section.start}–{section.end} 行{title}"
        total = item.known + len(item.unique)
        if item.kind == KIND_DUPLICATE:
            lines.append(f"{prefix} {where}：{total} 行全部已在配置库 → 默认：移除（先备份）")
        else:
            shared = f"，也出现在：{'、'.join(item.shared_with)}" if item.shared_with else ""
            lines.append(f"{prefix} {where}：{total} 行，其中 {len(item.unique)} 行独有{shared} → 需要选择：{'、'.join(item.choices)}")
            for line in item.unique[:5]:
                lines.append(f"        第 {line.number} 行：{line.text}")
            if len(item.unique) > 5:
                lines.append(f"        …… 另有 {len(item.unique) - 5} 行")
    for entry in plan.blocked:
        lines.append(f"  已跳过：{entry['instance']} · {entry['path']}：{_BLOCK_REASON.get(entry['reason'], entry['reason'])}")
    lines.append("")
    lines.append("加 --apply 执行默认动作（登记 agent、移除完全重复的段落）。")
    lines.append("独有内容用 --item <序号或编号> --choice adopt|keep|remove|skip 逐项处理，再加 --apply 执行。")
    return "\n".join(lines)
