"""Field-level difference display and ownership selection.

Differences are shown with Chinese field names, the shared value, the local
value and where each came from.  The user always chooses one of three outcomes:

* share to other devices — update the shared template
* this device only — write a local override
* restore the shared value — apply the shared value locally

Nothing is written before the user chooses, and a non-interactive caller must
pass an explicit choice and receives a stable status instead of a prompt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .utils import SECRET, json_bytes

#: Chinese labels for the managed fields shown to users.
FIELD_LABELS = {
    "approval_policy": "命令审批策略",
    "sandbox_mode": "沙箱模式",
    "web_search": "网页搜索",
    "model_reasoning_effort": "推理强度",
    "project_doc_max_bytes": "项目说明文档上限",
    "autoMemoryEnabled": "自动记忆开关",
    "rules": "公共规则",
}

TOOL_LABELS = {"codex": "Codex", "claude": "Claude"}

CHOICES = ("share", "local", "restore")

CHOICE_LABELS = {
    "share": "共享到其他设备",
    "local": "仅此设备",
    "restore": "恢复共享值",
}

#: Complex structures are displayed but never auto-merged in the first version.
COMPLEX_TYPES = (dict, list)


class DiffChoiceError(ValueError):
    """The caller asked for an outcome that is not well defined."""


@dataclass(frozen=True)
class FieldDiff:
    """One managed field that differs between the source and this device."""

    tool: str
    field: str
    shared_value: Any
    local_value: Any
    source: str
    complex_value: bool = False

    @property
    def label(self) -> str:
        return FIELD_LABELS.get(self.field, self.field)

    @property
    def tool_label(self) -> str:
        return TOOL_LABELS.get(self.tool, self.tool)

    @property
    def choices(self) -> tuple[str, ...]:
        """The ownership outcomes that are actually valid for this row.

        A hand-edited rules block has no sensible "this device only": the other
        devices would keep reporting the shared value as current, which is the
        silent divergence the block cannot represent.  Offering it here would
        send the user into a refusal.
        """
        if self.field == "rules":
            return ("share", "restore")
        return CHOICES

    def masked(self) -> "FieldDiff":
        """Return a copy safe for display: sensitive values are hidden."""
        if _looks_sensitive(self.field, self.shared_value) or _looks_sensitive(self.field, self.local_value):
            return FieldDiff(self.tool, self.field, "（已遮蔽）", "（已遮蔽）", self.source, self.complex_value)
        return self

    def describe(self) -> list[str]:
        safe = self.masked()
        origin = {
            "template": "来自共享模板",
            "platform": "来自平台差异",
            "local": "来自本机覆盖",
            "unset": "两侧都未设置",
        }.get(self.source, self.source)
        lines = [f"{safe.tool_label} · {safe.label}（{self.field}）—— {origin}"]
        lines.append(f"    共享值：{_render(safe.shared_value)}")
        lines.append(f"    本机值：{_render(safe.local_value)}")
        if safe.complex_value:
            lines.append("    该项为复杂结构，第一版只展示，请用高级方式处理，不会自动合并。")
        if self.field == "rules":
            lines.append(
                "    受管规则区块只能整体处理：share=把本机版本作为共享值（需合并进 common/），"
                "restore=恢复共享值（会先备份本机文件）。"
            )
        return lines


def _render(value: Any) -> str:
    if value is None:
        return "（未设置）"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, COMPLEX_TYPES):
        return "复杂结构（见高级说明）"
    return str(value)


def is_sensitive_value(field_name: str, value: Any) -> bool:
    """Whether a field name or value must never leave this device.

    Shared by the diff display (which masks such values) and the ownership
    persistence path (which refuses to write them), so the two can never
    disagree about what is safe.
    """
    lowered = field_name.casefold()
    if any(token in lowered for token in ("token", "secret", "password", "key", "credential")):
        return True
    if isinstance(value, str):
        return bool(SECRET.search(value))
    if isinstance(value, COMPLEX_TYPES):
        return any(is_sensitive_value(field_name, item) for item in (value if isinstance(value, list) else value.values()))
    return False


def _looks_sensitive(field_name: str, value: Any) -> bool:
    return is_sensitive_value(field_name, value)


def collect_diffs(
    *,
    shared: Mapping[str, Mapping[str, Any]],
    local: Mapping[str, Mapping[str, Any]],
    tools: Iterable[str] = (),
    rules: Iterable[Mapping[str, Any]] = (),
    overrides: Mapping[str, Iterable[str]] = {},
) -> list[FieldDiff]:
    """Compare the shared template against this device's effective values.

    Only managed fields are compared.  Selecting different unmanaged fields, or
    having legitimate platform/path differences, must not appear here.

    ``rules`` carries detected managed-rules-block drift, because editing the
    rules block is the most common local modification and it must be visible
    here — otherwise a user told to "run diff" would see nothing to resolve.

    ``overrides`` names the fields this device already decided to keep locally,
    so the display does not claim such a value came from the shared template.
    """
    diffs: list[FieldDiff] = []
    for tool in sorted(set(tools) | set(shared) | set(local)):
        shared_values = shared.get(tool, {}) or {}
        local_values = local.get(tool, {}) or {}
        device_only = set(overrides.get(tool, ()) or ())
        for name in sorted(set(shared_values) | set(local_values)):
            shared_value = shared_values.get(name)
            local_value = local_values.get(name)
            if shared_value == local_value:
                continue
            if name in device_only:
                source = "local"
            elif name in local_values and name not in shared_values:
                source = "local"
            elif name in shared_values and name not in local_values:
                source = "unset"
            else:
                source = "template"
            diffs.append(FieldDiff(
                tool=tool,
                field=name,
                shared_value=shared_value,
                local_value=local_value,
                source=source,
                complex_value=isinstance(shared_value, COMPLEX_TYPES) or isinstance(local_value, COMPLEX_TYPES),
            ))
    for record in rules:
        tool = str(record.get("tool", ""))
        diffs.append(FieldDiff(
            tool=tool,
            field="rules",
            shared_value="（共享规则区块，见 common/）",
            local_value="（本机在受管区块内改过内容）",
            source="target_file",
            complex_value=True,
        ))
    return diffs


def render_diffs(diffs: Iterable[FieldDiff]) -> str:
    items = list(diffs)
    if not items:
        return "没有需要处理的字段差异。本机受管配置与共享值一致。"
    lines = [f"发现 {len(items)} 处受管字段差异：", ""]
    for diff in items:
        lines.extend(diff.describe())
        lines.append("")
    # Only advertise choices that every listed row accepts, so the hint never
    # sends the user into a refusal.
    offered = {"share", "local", "restore"}
    for diff in items:
        offered &= set(diff.choices)
    if not offered:
        offered = {"share", "restore"}
    ordered = [choice for choice in CHOICES if choice in offered]
    lines.append("请选择每一项的处理方式：" + "、".join(f"{key}={CHOICE_LABELS[key]}" for key in ordered))
    return "\n".join(lines).rstrip()


def resolve_choice(choice: str, *, field_name: str, shared_value: Any) -> dict[str, Any]:
    """Translate a user choice into a concrete, explicit action.

    The result states what will be written and what it affects so the caller
    never has to guess, and the effect list is shown before any write.
    """
    if choice not in CHOICES:
        raise DiffChoiceError(f"未知的处理方式：{choice}；可选：{'、'.join(CHOICES)}")
    if choice == "share":
        return {
            "choice": "share",
            "field": field_name,
            "target": "shared_template",
            "value": shared_value,
            "effect": "更新共享模板字段，其他设备在下一次同步后会得到该值。",
        }
    if choice == "local":
        return {
            "choice": "local",
            "field": field_name,
            "target": "local_override",
            "value": shared_value,
            "effect": "写入本机覆盖，只影响这台设备，不修改共享模板。",
        }
    return {
        "choice": "restore",
        "field": field_name,
        "target": "local_effective",
        "value": shared_value,
        "effect": "先备份本机文件，再应用共享值；本机当前值可在恢复中找回。",
    }


def non_interactive_status(diffs: Iterable[FieldDiff], *, choice: str | None) -> dict[str, Any]:
    """Stable status for automation; a missing choice never silently writes."""
    items = list(diffs)
    if not items:
        return {"status": "no_changes", "ready": True, "count": 0}
    if choice is None:
        return {
            "status": "choice_required",
            "ready": False,
            "count": len(items),
            "message": "非交互模式必须显式指定处理方式（share、local 或 restore）。",
        }
    if choice not in CHOICES:
        return {"status": "invalid_choice", "ready": False, "count": len(items), "message": f"未知的处理方式：{choice}"}
    return {"status": "ready", "ready": True, "count": len(items), "choice": choice}
