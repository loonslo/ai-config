"""Unified Chinese error and next-step messages for every CLI entry point.

Every user-facing failure is rendered in the fixed shape
"发生了什么 / 原数据是否保留 / 下一步怎么做" and carries a stable error code.
JSON output uses the same codes so automation and humans agree.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class Message:
    """A single actionable message with a stable code."""

    code: str
    what: str
    preserved: str
    next_step: str
    exit_code: int = 1
    level: str = "error"
    detail: str | None = None

    def lines(self, *, verbose: bool = False) -> list[str]:
        head = "错误" if self.level == "error" else "提示" if self.level == "warning" else "信息"
        output = [
            f"[{self.code}] {head}：{self.what}",
            f"  原有数据：{self.preserved}",
            f"  下一步：{self.next_step}",
        ]
        if verbose and self.detail:
            output.append(f"  技术详情：{self.detail}")
        return output

    def as_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "level": self.level,
            "what": self.what,
            "preserved": self.preserved,
            "next_step": self.next_step,
            "detail": self.detail,
            "exit_code": self.exit_code,
        }


#: Stable error catalogue.  Codes never change meaning between releases.
CATALOGUE: dict[str, Message] = {
    "E1001": Message(
        "E1001",
        "本机还没有完成首次设置。",
        "没有文件被修改。",
        "运行 ai-config 的 setup 向导完成首次设置。",
        exit_code=2,
    ),
    "E1002": Message(
        "E1002",
        "目标工具目录不存在，或未选择任何共享范围。",
        "没有文件被修改，也没有创建工具目录。",
        "先安装并启动目标工具，使其生成配置目录，再重新设置。",
        exit_code=2,
    ),
    "E2001": Message(
        "E2001",
        "无法连接配置源或 Git 远端（网络不可用、认证失败或远端不存在）。",
        "本机已应用的配置和已保存的填写内容都保留。",
        "检查网络与仓库权限后重试；已填写的信息不会丢失。",
        exit_code=3,
    ),
    "E2002": Message(
        "E2002",
        "配置源存在未提交的修改，或远端与本地已分叉。",
        "双方内容都保留，没有强制覆盖。",
        "本机共享修改可用 sync --publish 提交并发布；远端分叉需先人工合并，再运行一次同步。",
        exit_code=4,
    ),
    "E3001": Message(
        "E3001",
        "工具目标文件中的受管内容与本机期望不一致（配置漂移）。",
        "本机目标文件未被改动，原有内容完整保留。",
        "运行 diff 查看字段差异并选择处理方式（share / local / restore），再重新同步。",
        exit_code=4,
    ),
    "E3002": Message(
        "E3002",
        "目标文件缺失、格式错误或无法读取，应用无法完成核验。",
        "没有生成成功回执，已有备份保留。",
        "确认目标文件路径可写且格式正确后重试；缺失文件会先重建再应用。",
        exit_code=2,
    ),
    "E3003": Message(
        "E3003",
        "写入目标文件失败（文件被占用或权限不足）。",
        "本批次已回滚到写入前的状态，备份保留。",
        "关闭正在使用该文件的工具窗口，然后重试。",
        exit_code=1,
    ),
    "E4001": Message(
        "E4001",
        "备份内容不完整或已损坏，无法安全恢复。",
        "当前文件保持原样，没有被恢复覆盖。",
        "改用其他备份或手动恢复；确认前不要删除现有文件。",
        exit_code=2,
    ),
    "E4002": Message(
        "E4002",
        "存在未完成的事务，需要先处理才能继续。",
        "所有已写入文件保留，未继续写入。",
        "运行恢复流程（doctor --recover）处理未完成事务后再重试。",
        exit_code=2,
    ),
    "E5001": Message(
        "E5001",
        "状态尚未上报到共享源。",
        "本机已应用的配置仍然有效。",
        "网络恢复后重试上报；本机状态不受影响。",
        exit_code=3,
        level="warning",
    ),
    "E1003": Message(
        "E1003",
        "已登记的 agent 暂时找不到规则入口（例如 TRAE 还没有创建过全局规则）。",
        "没有文件被修改，也没有创建任何目录。",
        "按 status 中的提示在该 agent 里完成一次设置（例如 TRAE 设置 → 规则 → 创建全局规则），再运行 sync。",
        2,
        "warning",
    ),
    "E3004": Message(
        "E3004",
        "目标位置已有一个不是由 ai-config 创建的文件，不能接管。",
        "该文件没有被修改。",
        "先运行 migrate 预览并处理已有内容（adopt / keep / remove），或用 scan 确认这个文件的来源后再同步。",
        4,
        "conflict",
    ),
    "E6001": Message(
        "E6001",
        "加载核验未通过：agent 回答的规则版本与本机应用的版本不一致。",
        "没有文件被修改。",
        "确认已运行 sync --apply，关闭并重新开启该 agent 的会话后再核验；仍不通过时运行 scan 检查规则入口位置。",
        2,
        "error",
    ),
    "E9001": Message(
        "E9001",
        "发生了未分类错误。",
        "没有写入未经验证的文件。",
        "使用 --verbose 查看技术详情，或运行 doctor 检查本机状态。",
        exit_code=1,
    ),
}


def get(code: str, *, detail: str | None = None) -> Message:
    base = CATALOGUE.get(code)
    if base is None:
        raise KeyError(f"Unknown message code: {code}")
    if detail is None:
        return base
    return Message(base.code, base.what, base.preserved, base.next_step, base.exit_code, base.level, detail)


def render(message: Message, *, verbose: bool = False) -> str:
    return "\n".join(message.lines(verbose=verbose))


def render_many(messages: Iterable[Message], *, verbose: bool = False) -> str:
    return "\n".join(render(message, verbose=verbose) for message in messages)


def error_for_exit(code: int) -> Message:
    """Map a legacy exit code onto a catalogue entry."""
    mapping = {2: "E1001", 3: "E2001", 4: "E2002"}
    return get(mapping.get(code, "E9001"))


def from_exception(error: BaseException, *, exit_code: int | None = None) -> Message:
    """Classify an exception into the catalogue without leaking a traceback."""
    text = str(error)
    lowered = text.casefold()
    code = "E9001"
    if any(token in lowered for token in ("not a git", "no such", "missing", "not found", "not ready", "incomplete", "尚未", "未设置")):
        code = "E1001"
    if any(token in lowered for token in ("network", "remote", "push", "fetch", "offline", "cannot fetch")):
        code = "E2001"
    if any(token in lowered for token in ("diverg", "dirty", "uncommitted", "fork")):
        code = "E2002"
    if "conflict" in lowered or "collision" in lowered:
        code = "E2002"
    if any(token in lowered for token in ("target", "drift", "projection", "managed")):
        code = "E3001"
    if any(token in lowered for token in ("permission", "denied", "占用", "locked", "access is denied")):
        code = "E3003"
    if any(token in lowered for token in ("backup", "corrupt", "hash mismatch")):
        code = "E4001"
    if any(token in lowered for token in ("transaction", "journal", "rollback_required")):
        code = "E4002"
    message = get(code, detail=text)
    if exit_code is not None:
        message = Message(message.code, message.what, message.preserved, message.next_step, exit_code, message.level, text)
    return message


#: Guidance shown after a successful configuration apply.  Download, apply and
#: session reload are deliberately three separate statements.
POST_APPLY_NOTES = (
    "共享配置已下载并写入本机目标文件。",
    "本机目标文件已核对：受管内容与共享值一致。",
    "工具需要启动新的会话才会加载新配置；当前会话不会自动生效。",
)


def next_step_for_status(status: str) -> str:
    mapping = {
        "not_configured": "运行 setup 向导完成首次设置。",
        "pending_sync": "运行一次同步以应用共享配置。",
        "applied": "无需操作。启动新工具会话即可加载最新配置。",
        "local_modified": "运行 status 查看本机差异，并选择保留本机值还是采用共享值。",
        "conflict": "先解决共享源与远端的分叉，再重新同步。",
        "offline": "网络恢复后重试；本机现有配置不受影响。",
        "apply_failed": "检查目标文件是否可写，然后重试应用。",
        "restart_required": "启动新的工具会话以加载已应用的新配置。",
    }
    return mapping.get(status, "运行 status 查看当前状态。")


def json_error(message: Message) -> str:
    return json.dumps(message.as_json(), ensure_ascii=False)
