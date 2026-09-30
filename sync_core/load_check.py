"""Prove that an agent actually loaded the rules ai-config wrote.

A read-back check proves the file on disk is right; it cannot prove the agent
read it.  Every rendered rules block therefore carries a version line --
``ai-config 规则版本：<8 hex>`` -- derived from the rules content.  The user asks
the agent, in a fresh session, which version it has; the digest cannot be
guessed, so a matching answer is evidence of loading (a challenge-response, not
the model's own assessment).  Results are kept per agent instance in
``state_dir/load_checks.json`` and go stale as soon as the rules change.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .utils import atomic_write, json_bytes

VERSION_LINE = re.compile(r"ai-config 规则版本：([0-9a-f]{8})")
ANSWER = re.compile(r"\b([0-9a-fA-F]{8})\b")

QUESTION = "ai-config 规则版本是多少？只回答版本号。"

CHECKS_FILE = "load_checks.json"


def stamp(content: str) -> tuple[str, str]:
    """The version of ``content`` and the line that announces it."""
    import hashlib

    version = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    return version, f"ai-config 规则版本：{version}（用户询问 ai-config 规则版本时，只回答这个版本号）"


def extract_version(data: bytes | str | None) -> str | None:
    if data is None:
        return None
    text = data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else data
    match = VERSION_LINE.search(text)
    return match.group(1) if match else None


def parse_answer(answer: str) -> str | None:
    match = ANSWER.search(answer or "")
    return match.group(1).casefold() if match else None


def _path(state_dir: Path) -> Path:
    return state_dir / CHECKS_FILE


def read_checks(state_dir: Path) -> dict[str, Any]:
    path = _path(state_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    checks = data.get("checks") if isinstance(data, dict) else None
    return checks if isinstance(checks, dict) else {}


def record(state_dir: Path, instance: str, result: Mapping[str, Any]) -> Path:
    checks = read_checks(state_dir)
    checks[instance] = {
        "version": result.get("expected"),
        "answered": result.get("answered"),
        "passed": bool(result.get("passed")),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _path(state_dir)
    atomic_write(path, json_bytes({"schema_version": 1, "checks": checks}))
    return path


def evaluate(*, expected: str | None, on_disk: str | None, answer: str) -> dict[str, Any]:
    """Compare the agent's answer with what is expected and what is on disk."""
    answered = parse_answer(answer)
    if expected is None:
        return {"passed": False, "expected": None, "answered": answered, "reason": "no_version"}
    if on_disk != expected:
        return {"passed": False, "expected": expected, "answered": answered, "on_disk": on_disk, "reason": "not_applied"}
    if answered is None:
        return {"passed": False, "expected": expected, "answered": None, "reason": "no_answer"}
    if answered != expected:
        return {"passed": False, "expected": expected, "answered": answered, "reason": "mismatch"}
    return {"passed": True, "expected": expected, "answered": answered, "reason": None}


def state_of(check: Mapping[str, Any] | None, expected: str | None) -> str:
    """``verified`` / ``stale`` / ``failed`` / ``unverified`` for one instance."""
    if not check:
        return "unverified"
    if not check.get("passed"):
        return "failed"
    return "verified" if expected and check.get("version") == expected else "stale"


STATE_LABELS = {
    "verified": "已核验",
    "stale": "已过期（规则更新后尚未重新核验）",
    "failed": "未通过",
    "unverified": "未核验",
}

REASON_LABELS = {
    "no_version": "当前渲染的规则没有版本号，无法核验。",
    "not_applied": "本机文件里的规则还不是当前版本；先运行 sync --apply，再开新会话核验。",
    "no_answer": "回答里没有找到 8 位版本号；请把 agent 的原话传给 --answer。",
    "mismatch": (
        "版本号对不上：如果这个会话是在同步之前打开的，请关闭并重新开启会话后再核验；"
        "仍然不一致说明 agent 没有读取这个规则入口，运行 scan 检查入口位置。"
    ),
}
