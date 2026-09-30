"""Read-only inventory of every AI agent on this host.

``scan`` answers "what is already configured on this machine" before anything
is migrated or taken over:

* which agents and instances exist, where, and whether ai-config manages them;
* the state of each rules entry and of the rules the user wrote by hand,
  compared line by line with the configuration store;
* persona, memory, settings and skills, listed by name only;
* credential and runtime material, listed by name only and never opened.

Nothing is written unless the caller persists the report explicitly.  The only
files whose content is read are rules Markdown files and ``SKILL.md`` files
(hashed, never printed), and a rules file that looks like it holds a secret is
reported as blocked with its content withheld.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import uuid
from typing import Any, Iterable, Mapping

from . import agents, rules_text
from .agents import AgentInstance, AgentProfile, DetectedInstance, HostEnv
from .utils import SECRET, atomic_write, digest, json_bytes

SCHEMA_VERSION = 1

#: Skill directories shared across agents rather than owned by one of them.
SHARED_SKILL_DIRS = (("agents-standard", "{home}/.agents/skills"),)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())
    except OSError:
        return False


def _link_target(path: Path) -> str | None:
    try:
        target = os.readlink(path)
    except OSError:
        return None
    # Windows junctions report an extended-length prefix.
    return target[4:] if target.startswith("\\\\?\\") else target


def display_path(path: Path | str | None, host: HostEnv) -> str | None:
    if path is None:
        return None
    text = str(path)
    home = str(host.home)
    if text.casefold().startswith(home.casefold()):
        return "~" + text[len(home):].replace("\\", "/")
    return text


# --------------------------------------------------------------------------
# rules analysis
# --------------------------------------------------------------------------

def _read_rules_file(path: Path) -> tuple[bytes | None, str | None]:
    """Read a rules Markdown file, or explain why it was not read."""
    if _is_link(path):
        return None, "symlink"
    try:
        data = path.read_bytes()
    except OSError:
        return None, "unreadable"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, "not_utf8"
    if SECRET.search(text):
        return None, "blocked_secret"
    return data, None


def analyze_rules_file(path: Path, known_keys: set[str], *, relative: str, role: str) -> dict[str, Any]:
    """Compare one rules file with the store, never exposing its content."""
    record: dict[str, Any] = {"path": relative, "role": role, "exists": path.is_file()}
    if not record["exists"]:
        record["status"] = "missing"
        return record
    data, problem = _read_rules_file(path)
    if problem is not None:
        record["status"] = problem
        return record
    outside = rules_text.outside_block(data)
    comparison = rules_text.compare(outside.lines(), known_keys)
    record.update({
        "status": "ok" if outside.block_error is None else "malformed_block",
        "has_managed_block": outside.has_block,
        "lines": comparison.total,
        "known_lines": len(comparison.known),
        "unique_lines": len(comparison.unique),
        "digest": digest(data),
    })
    return record


def _existing_rule_files(root: Path, profile: AgentProfile, entry: Path | None) -> list[tuple[Path, str]]:
    """Hand-written rules files an agent loads, excluding ai-config's own file."""
    found: list[tuple[Path, str]] = []
    for relative in profile.existing_rules:
        path = root / relative
        if _is_link(path):
            continue
        if path.is_dir():
            for item in sorted(path.rglob("*.md")):
                if item.is_file() and not _is_link(item) and item.name != agents.OWNED_FILE_NAME:
                    found.append((item, item.relative_to(root).as_posix()))
        elif path.is_file():
            found.append((path, relative))
    if entry is not None:
        found = [(path, relative) for path, relative in found if path != entry]
    return found


# --------------------------------------------------------------------------
# per-agent report
# --------------------------------------------------------------------------

def _classify(profile: AgentProfile, name: str, rules_names: set[str]) -> str:
    if name in rules_names:
        return "rules"
    if agents.is_sensitive(profile, name):
        return "protected"
    for group in ("persona", "memory", "skills", "settings"):
        if agents.matches(name, getattr(profile, group)):
            return group
    if agents.matches(name, profile.runtime):
        return "runtime"
    return "other"


def _entries(root: Path) -> list[str]:
    try:
        return sorted(item.name for item in root.iterdir())
    except OSError:
        return []


def _protected_names(root: Path, profile: AgentProfile) -> list[str]:
    names = {name for name in _entries(root) if agents.is_sensitive(profile, name)}
    # Nested protected locations (``app/connector-keys``) are checked by
    # existence only; their parent is otherwise just runtime data.
    for pattern in (*agents.COMMON_SENSITIVE, *profile.sensitive):
        if "/" in pattern and not any(char in pattern for char in "*?[") and (root / pattern).exists():
            names.add(pattern)
    return sorted(names)


def _count_markdown(path: Path) -> int:
    """Memory is Markdown; transcripts and caches next to it are not counted."""
    if not path.is_dir() or _is_link(path):
        return 1 if path.is_file() and path.suffix.casefold() == ".md" else 0
    try:
        return sum(1 for item in path.rglob("*.md") if item.is_file())
    except OSError:
        return 0


def _instance_for(detected: DetectedInstance) -> AgentInstance:
    return AgentInstance(detected.instance, detected.profile, detected.root, agents._topics(None, detected.profile), detected.profile.rules, detected.instance in agents.LEGACY_INSTANCES)


def _agent_report(
    instance: AgentInstance,
    *,
    detected: DetectedInstance | None,
    managed: bool,
    known_keys: set[str],
    host: HostEnv,
) -> dict[str, Any]:
    profile = instance.profile
    root = instance.root
    exists = root.is_dir()
    report: dict[str, Any] = {
        "instance": instance.id,
        "profile": profile.id,
        "name": agents.display_name(instance.id) if profile.id != agents.GENERIC else instance.id,
        "level": profile.level,
        "kind": profile.kind,
        "root": display_path(root, host),
        "origin": detected.origin if detected and detected.root == root else "设备配置",
        "installed": bool(detected.installed) if detected else exists,
        "root_exists": exists,
        "executable": bool(detected.executable) if detected else False,
        "managed": managed,
        "evidence": profile.evidence,
    }
    if profile.manages:
        report["manages"] = list(profile.manages)
    if not profile.writable or not exists:
        return report

    reason = agents.unresolved_reason(instance)
    entry = agents.rules_target(instance)
    rules: dict[str, Any] = {"mode": entry.mode if entry else None, "kind": entry.kind if entry else None}
    if entry is None or reason:
        rules.update({"state": "unresolved", "reason": reason})
    else:
        rules["entry"] = entry.path.relative_to(root).as_posix()
        analysis = analyze_rules_file(entry.path, known_keys, relative=rules["entry"], role="entry")
        rules["analysis"] = analysis
        if not analysis["exists"]:
            rules["state"] = "missing"
        elif analysis["status"] != "ok":
            rules["state"] = analysis["status"]
        elif entry.mode == agents.MODE_FILE and not analysis["has_managed_block"]:
            rules["state"] = "foreign"
        elif analysis.get("has_managed_block"):
            rules["state"] = "managed"
        else:
            rules["state"] = "unmanaged"
    report["rules"] = rules

    existing = [
        analyze_rules_file(path, known_keys, relative=relative, role="existing")
        for path, relative in _existing_rule_files(root, profile, entry.path if entry else None)
    ]
    report["existing_rules"] = existing
    shadowing = [name for name in profile.shadowed_by if (root / name).exists()]
    if shadowing:
        report["shadowed_by"] = shadowing

    rules_names = {path.split("/", 1)[0] for path in [rules.get("entry", ""), *(item["path"] for item in existing)] if path}
    groups: dict[str, list[str]] = {"persona": [], "memory": [], "skills": [], "settings": [], "runtime": [], "other": []}
    for name in _entries(root):
        group = _classify(profile, name, rules_names)
        if group in groups:
            groups[group].append(name)
    report["persona"] = groups["persona"]
    report["memory"] = [{"path": name, "files": _count_markdown(root / name)} for name in groups["memory"]]
    report["settings"] = groups["settings"]
    report["protected"] = _protected_names(root, profile)
    report["runtime_entries"] = len(groups["runtime"])
    report["other"] = groups["other"]
    report["migratable"] = [
        item["path"]
        for item in ([rules["analysis"]] if "analysis" in rules else []) + existing
        if item.get("status") == "ok" and item.get("lines")
    ]
    return report


# --------------------------------------------------------------------------
# skills (inventory only)
# --------------------------------------------------------------------------

def _skill_sources(detected: Iterable[DetectedInstance], host: HostEnv) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for item in detected:
        if not item.exists:
            continue
        for relative in item.profile.skills:
            path = item.root / relative
            if path.exists() or _is_link(path):
                sources.append({"owner": item.instance, "path": path})
    for owner, template in SHARED_SKILL_DIRS:
        path = host.expand(template)
        if path is not None and (path.exists() or _is_link(path)):
            sources.append({"owner": owner, "path": path})
    return sources


def _managed_by(target: str | None, sources: list[dict[str, Any]]) -> str | None:
    if not target:
        return None
    normalized = str(Path(target)).replace("\\", "/").rstrip("/").casefold()
    for source in sources:
        if str(source["path"]).replace("\\", "/").rstrip("/").casefold() == normalized:
            return str(source["owner"])
    return None


def skills_inventory(detected: Iterable[DetectedInstance], host: HostEnv) -> dict[str, Any]:
    sources = _skill_sources(list(detected), host)
    rows: list[dict[str, Any]] = []
    copies: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        path: Path = source["path"]
        row: dict[str, Any] = {"owner": source["owner"], "path": display_path(path, host), "skills": 0}
        if _is_link(path):
            # A linked skills directory belongs to whoever owns its target; it is
            # counted there, not twice.
            target = _link_target(path)
            row.update({"link": True, "link_target": display_path(target, host), "managed_by": _managed_by(target, sources)})
            rows.append(row)
            continue
        try:
            children = sorted(child for child in path.iterdir() if child.is_dir() and not child.name.startswith("."))
        except OSError:
            row["status"] = "unreadable"
            rows.append(row)
            continue
        for child in children:
            skill = child / "SKILL.md"
            if not skill.is_file() or _is_link(child) or _is_link(skill):
                continue
            try:
                data = skill.read_bytes()
            except OSError:
                continue
            row["skills"] += 1
            copies.setdefault(child.name, []).append({"owner": source["owner"], "digest": digest(data)})
        rows.append(row)
    skills = []
    for name, found in sorted(copies.items()):
        digests = {item["digest"] for item in found}
        if len(found) == 1:
            state = "unique"
        elif len(digests) == 1:
            state = "duplicate"
        else:
            state = "conflict"
        skills.append({"name": name, "state": state, "owners": sorted({item["owner"] for item in found})})
    summary = {state: sum(item["state"] == state for item in skills) for state in ("unique", "duplicate", "conflict")}
    summary["total"] = len(skills)
    return {"sources": rows, "skills": skills, "summary": summary, "writes": False}


# --------------------------------------------------------------------------
# scan
# --------------------------------------------------------------------------

def scan(host: HostEnv, *, store_root: Path, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Inventory every agent on ``host``; performs no writes."""
    known_keys = rules_text.store_keys(store_root)
    detected = agents.detect_instances(host)
    configured = {instance.id: instance for instance in agents.agent_instances(config or {})}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in detected:
        instance = configured.get(item.instance) or _instance_for(item)
        if not item.installed and item.instance not in configured:
            continue
        seen.add(item.instance)
        rows.append(_agent_report(instance, detected=item, managed=item.instance in configured, known_keys=known_keys, host=host))
    for instance_id, instance in configured.items():
        if instance_id not in seen:
            rows.append(_agent_report(instance, detected=None, managed=True, known_keys=known_keys, host=host))
    writable = [row for row in rows if row["level"] == agents.LEVEL_RULES]
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_id": uuid.uuid4().hex,
        "created_at": _now(),
        "system": host.system,
        "read_only": True,
        "store": display_path(store_root, host),
        "agents": rows,
        "skills": skills_inventory(detected, host),
        "summary": {
            "detected": len(rows),
            "writable": len(writable),
            "detect_only": sum(row["level"] == agents.LEVEL_DETECT for row in rows),
            "managed": sum(bool(row["managed"]) for row in rows),
            "migratable_files": sum(len(row.get("migratable", [])) for row in writable),
            "protected_items": sum(len(row.get("protected", [])) for row in writable),
        },
    }


def persist(report: Mapping[str, Any], state_dir: Path) -> Path:
    target = state_dir / "scans" / f"{report['scan_id']}.json"
    atomic_write(target, json_bytes(dict(report)))
    return target


# --------------------------------------------------------------------------
# Chinese rendering
# --------------------------------------------------------------------------

_RULES_STATE = {
    "managed": "已由 ai-config 接管",
    "unmanaged": "尚未接管",
    "missing": "尚未创建",
    "foreign": "已存在同名文件但不是 ai-config 创建的，接管前需先处理",
    "unresolved": "暂无法确定入口",
    "blocked_secret": "疑似包含凭据，已跳过（未输出内容）",
    "malformed_block": "受管区块标记损坏，需要人工检查",
    "not_utf8": "不是 UTF-8 文本，已跳过",
    "unreadable": "无法读取",
    "symlink": "是符号链接，不跟随",
}

_MODE_LABEL = {agents.MODE_BLOCK: "受管区块", agents.MODE_FILE: "独占文件"}


def _rules_line(analysis: Mapping[str, Any]) -> str:
    if analysis.get("status") != "ok":
        return _RULES_STATE.get(str(analysis.get("status")), str(analysis.get("status")))
    total = analysis.get("lines", 0)
    if not total:
        return "没有需要迁入的内容"
    known, unique = analysis.get("known_lines", 0), analysis.get("unique_lines", 0)
    return f"{total} 行手写内容，其中 {known} 行已在配置库，{unique} 行独有"


def render(report: Mapping[str, Any]) -> str:
    lines = [f"配置库：{report.get('store')}", ""]
    rows = list(report.get("agents", []))
    writable = [row for row in rows if row["level"] == agents.LEVEL_RULES]
    detect_only = [row for row in rows if row["level"] == agents.LEVEL_DETECT and row.get("kind") != "manager"]
    managers = [row for row in rows if row.get("kind") == "manager"]

    lines.append("可接管的 agent（规则入口）：")
    if not writable:
        lines.append("  未发现。")
    for row in writable:
        state = "本机已登记" if row["managed"] else "本机未登记"
        if not row.get("root_exists"):
            state += "（配置目录不存在）"
        label = row["name"] if row["instance"] in row["name"] else f"{row['name']}（{row['instance']}）"
        lines.append(f"  {label}  {row['root']}  {state}")
        rules = row.get("rules")
        if rules:
            if rules.get("state") == "unresolved":
                lines.append(f"    规则入口：{rules.get('reason')}")
            else:
                mode = _MODE_LABEL.get(str(rules.get("mode")), str(rules.get("mode")))
                analysis = rules.get("analysis", {})
                detail = _RULES_STATE.get(str(rules.get("state")), str(rules.get("state")))
                extra = f"；区块外：{_rules_line(analysis)}" if analysis.get("exists") and analysis.get("status") == "ok" else ""
                lines.append(f"    规则入口：{rules.get('entry')}（{mode}，{detail}{extra}）")
        for item in row.get("existing_rules", []):
            lines.append(f"    已有规则：{item['path']}：{_rules_line(item)}")
        for name in row.get("shadowed_by", []):
            lines.append(f"    注意：存在 {name}，该 agent 会优先读取它，受管内容可能不生效")
        if row.get("persona"):
            lines.append("    人格文件（不管理）：" + "、".join(row["persona"]))
        if row.get("memory"):
            lines.append("    记忆（不管理）：" + "、".join(f"{item['path']}（{item['files']} 个 Markdown）" for item in row["memory"]))
        if row.get("settings"):
            lines.append("    设置文件（只列名称）：" + "、".join(row["settings"]))
        if row.get("protected"):
            lines.append("    受保护文件（只列名称，从未读取）：" + "、".join(row["protected"]))
        lines.append(f"    依据：{row['evidence']}")
    lines.append("")
    if detect_only:
        lines.append("仅识别（不写入）：")
        for row in detect_only:
            lines.append(f"  {row['name']}  {row['root']} —— {row['evidence']}")
        lines.append("")
    if managers:
        lines.append("管理类工具（共存，不触碰它接管的内容）：")
        for row in managers:
            lines.append(f"  {row['name']}  {row['root']}")
            for item in row.get("manages", []):
                lines.append(f"    接管：{item}")
        lines.append("")
    skills = report.get("skills", {})
    summary = skills.get("summary", {})
    lines.append("Skills 盘点（只读，本期不同步）：")
    lines.append(
        f"  共 {summary.get('total', 0)} 个：唯一 {summary.get('unique', 0)}、"
        f"多处相同 {summary.get('duplicate', 0)}、同名不同内容 {summary.get('conflict', 0)}"
    )
    for source in skills.get("sources", []):
        if source.get("link"):
            owner = f"，由 {source['managed_by']} 管理" if source.get("managed_by") else ""
            lines.append(f"  {source['owner']}：{source['path']} → {source.get('link_target')}（链接{owner}）")
        else:
            lines.append(f"  {source['owner']}：{source['path']}（{source['skills']} 个）")
    for item in skills.get("skills", []):
        if item["state"] == "conflict":
            lines.append(f"  同名不同内容：{item['name']}（{'、'.join(item['owners'])}）")
    lines.append("")
    total = report.get("summary", {})
    lines.append(
        f"合计：识别 {total.get('detected', 0)} 个，可接管 {total.get('writable', 0)} 个，"
        f"本机已登记 {total.get('managed', 0)} 个，可迁入的规则文件 {total.get('migratable_files', 0)} 个。"
    )
    lines.append("以上为只读盘点，没有写入任何文件。下一步：运行 migrate 预览迁入。")
    return "\n".join(lines)
