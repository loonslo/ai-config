"""Environment and tool detection for first-time setup.

Detection is strictly read-only: it never creates a tool configuration
directory that does not already exist, and it never installs anything.  Results
are turned into Chinese guidance that names the exact action for the current
platform instead of asking the user to guess a command.
"""
from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

MINIMUM_PYTHON = (3, 11)

#: Tool root environment variables that must be respected when set.
TOOL_ENV_VARS = {
    "codex": ("CODEX_HOME",),
    "claude": ("CLAUDE_CONFIG_DIR",),
}

DEFAULT_TOOL_ROOTS = {
    "codex": ".codex",
    "claude": ".claude",
}

REQUIRED_MODULES = ("tomlkit",)


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def system_name() -> str:
    system = platform.system().casefold()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    return system or "unknown"


def resolve_tool_root(tool: str, configured: str | None, home: Path) -> tuple[Path, str]:
    """Resolve a tool root, honouring the tool's own environment variable.

    Returns the resolved path and where it came from so the wizard can show the
    user which source won.
    """
    for variable in TOOL_ENV_VARS.get(tool, ()):
        value = __import__("os").environ.get(variable)
        if value:
            return Path(value).expanduser(), f"环境变量 {variable}"
    if configured:
        return Path(configured).expanduser(), "设备配置"
    return home / DEFAULT_TOOL_ROOTS[tool], "默认位置"


def detect(
    *,
    configured: Mapping[str, Any] | None = None,
    home: Path | None = None,
    project_root: Path | None = None,
    host: Any = None,
) -> dict[str, Any]:
    """Inspect the machine and the tools; performs no writes.

    Codex and Claude are always listed (installed or not).  Every other agent
    from the registry is listed only when its own configuration directory
    exists, because only then can its rules entry be taken over.
    """
    from .agents import LEGACY_INSTANCES, PROFILES, HostEnv, detect_instances, display_name

    raw = dict(configured or {})
    home = home or Path.home()
    host = host or HostEnv.for_home(home)
    python_ok = sys.version_info >= MINIMUM_PYTHON
    missing_modules = sorted(name for name in REQUIRED_MODULES if not _module_available(name))
    system = system_name()

    tools: list[dict[str, Any]] = []
    for tool in ("codex", "claude"):
        configured_value = raw.get(tool)
        root, origin = resolve_tool_root(tool, configured_value, home)
        executable = shutil.which(tool)
        exists = root.exists() and root.is_dir()
        # A tool that is not present is reported, never created.
        tools.append({
            "tool": tool,
            "root": str(root),
            "root_origin": origin,
            "root_exists": exists,
            "executable": executable,
            "installed": bool(executable) or exists,
            "configured": bool(configured_value),
        })
    others = [profile for profile in PROFILES.values() if profile.writable and profile.id not in LEGACY_INSTANCES]
    for item in detect_instances(host, profiles=others):
        if not item.exists:
            continue
        tools.append({
            "tool": item.instance,
            "name": display_name(item.instance),
            "root": str(item.root),
            "root_origin": item.origin,
            "root_exists": True,
            "executable": item.executable,
            "installed": True,
            "configured": bool((raw.get("agents") or {}).get(item.instance)),
        })

    dependencies = {
        "python": {
            "ok": python_ok,
            "version": platform.python_version(),
            "required": ".".join(str(part) for part in MINIMUM_PYTHON),
        },
        "modules": {
            "ok": not missing_modules,
            "missing": missing_modules,
        },
        "git": {
            "ok": shutil.which("git") is not None,
            "executable": shutil.which("git"),
        },
    }

    report = {
        "schema_version": 1,
        "system": system,
        "read_only": True,
        "dependencies": dependencies,
        "tools": tools,
        "ready": python_ok and not missing_modules and bool(dependencies["git"]["ok"]),
    }
    report["guidance"] = guidance(report, project_root=project_root)
    return report


def guidance(report: Mapping[str, Any], *, project_root: Path | None = None) -> list[dict[str, str]]:
    """Turn detection results into concrete, platform-appropriate steps."""
    system = report.get("system", "unknown")
    dependencies = report.get("dependencies", {})
    messages: list[dict[str, str]] = []

    python = dependencies.get("python", {})
    if not python.get("ok"):
        if system == "windows":
            action = f"安装 Python {python.get('required', '3.11')} 或更高版本，安装时勾选 Add python.exe to PATH，然后重新运行 ai-config.ps1。"
        else:
            action = f"用包管理器安装 Python {python.get('required', '3.11')} 或更高版本（例如 brew install python），然后重新运行 ai-config.command。"
        messages.append({"level": "error", "code": "PYTHON_TOO_OLD", "message": f"当前 Python 版本为 {python.get('version')}，需要 {python.get('required')} 或更高。", "action": action})

    modules = dependencies.get("modules", {})
    if not modules.get("ok"):
        missing = "、".join(modules.get("missing", []))
        command = "python -m pip install -r requirements.txt" if system == "windows" else "python3 -m pip install -r requirements.txt"
        messages.append({"level": "error", "code": "PACKAGE_MISSING", "message": f"缺少运行依赖：{missing}。", "action": f"在项目目录执行：{command}"})

    git = dependencies.get("git", {})
    if not git.get("ok"):
        if system == "windows":
            action = "安装 Git for Windows（https://git-scm.com/download/win），安装后重开终端再运行 ai-project 启动脚本。"
        else:
            action = "安装 Git（例如在 macOS 执行 brew install git），然后重新运行 ai-config.command。"
        messages.append({"level": "error", "code": "GIT_MISSING", "message": "未找到 git 命令，无法同步共享配置。", "action": action})

    installed = [tool for tool in report.get("tools", []) if tool.get("installed")]
    if not installed:
        messages.append({
            "level": "warning",
            "code": "NO_TOOL_DETECTED",
            "message": "未检测到可接管的 AI agent 配置目录（Codex、Claude Code、CodeBuddy、WorkBuddy、TRAE）。",
            "action": "先安装并至少启动一次目标工具，使其生成配置目录，然后重新检测。未安装的工具不会自动创建配置。",
        })
    else:
        names = "、".join(tool["tool"] for tool in installed)
        messages.append({"level": "info", "code": "TOOLS_DETECTED", "message": f"已检测到工具：{names}。", "action": "继续下一步选择共享范围。"})

    custom = [tool for tool in report.get("tools", []) if tool.get("root_origin") == "环境变量"]
    for tool in custom:
        messages.append({
            "level": "info",
            "code": "CUSTOM_TOOL_ROOT",
            "message": f"{tool['tool']} 使用自定义目录：{tool['root']}（来自{tool['root_origin']}）。",
            "action": "确认该目录正确；如需更换，请设置对应环境变量或设备配置中的路径。",
        })
    return messages


def missing_dependency_exit(report: Mapping[str, Any]) -> int:
    """Stable exit code for an unusable environment."""
    return 2 if not report.get("ready") else 0
