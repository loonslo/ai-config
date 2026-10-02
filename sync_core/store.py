"""Create or join a configuration store: the path every agent takes its rules from.

The store is a directory with the standard layout (``common/`` topics, the
Codex/Claude templates, optional ``agents.toml``). Local use is a plain folder;
an existing Git remote may be cloned when the user explicitly supplies one.
Keeping it apart from the tool's own checkout means a new user never has to
fork ai-config to own their rules.

Nothing is created implicitly: ``setup --store`` states which store to use, and
a directory that exists but is not a store is never taken over.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "store"

_GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "GCM_INTERACTIVE": "never"}


class StoreError(RuntimeError):
    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def default_store() -> Path:
    from .layout import default_store_path

    return default_store_path()


def required_files() -> list[str]:
    from .config import SHARED_RULE_TOPICS

    return [f"common/{topic}.md" for topic in SHARED_RULE_TOPICS]


def is_store(path: Path) -> bool:
    return path.is_dir() and all((path / relative).is_file() for relative in required_files())


def _check_local_path(path: Path) -> None:
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise StoreError(f"配置库路径包含符号链接；为避免写到其他位置，请选择实际目录：{path}", exit_code=4)


def plan_store(target: Path, *, remote: str | None) -> dict[str, Any]:
    """Decide what ``setup`` would do with ``target``; writes nothing."""
    _check_local_path(target)
    if is_store(target):
        return {"action": "use", "path": str(target), "detail": "使用已有配置库。"}
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise StoreError(f"目录已存在但不是 ai-config 配置库，不会接管：{target}", exit_code=4)
    if remote:
        return {"action": "clone", "path": str(target), "remote": remote, "detail": "从远端克隆已有配置库。"}
    return {"action": "create", "path": str(target), "detail": "在本机新建配置库；离线使用不需要 Git。"}


def _git(args: list[str], *, cwd: Path | None = None, timeout: float = 120.0) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_GIT_ENV,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise StoreError("Git 无法执行或超时；配置库没有创建。", exit_code=3) from error


def execute(plan: dict[str, Any]) -> Path:
    """Carry out a store plan from ``plan_store``."""
    target = Path(plan["path"])
    _check_local_path(target)
    if plan["action"] == "use":
        return target
    if plan["action"] == "clone":
        target.parent.mkdir(parents=True, exist_ok=True)
        result = _git(["clone", "--quiet", str(plan["remote"]), str(target)])
        if result.returncode:
            # stderr may contain a credentialed URL; it is not shown.
            raise StoreError("克隆配置库失败（地址不可达、需要认证或不存在）；本机没有写入配置。", exit_code=3)
        if not is_store(target):
            raise StoreError(f"克隆下来的仓库缺少配置库文件（{', '.join(required_files())}），请确认地址是 ai-config 配置库。", exit_code=2)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise StoreError(f"目标目录在预览后已有内容；不会合并或覆盖：{target}", exit_code=4)
    shutil.copytree(TEMPLATE, target, dirs_exist_ok=target.exists())
    return target
