"""Inventory third-party items by name and safe metadata, without copying them."""
from __future__ import annotations

import json
import ntpath
import os
from pathlib import Path
import re
import subprocess
import tomllib
from typing import Any, Mapping
from urllib.parse import urlsplit

from .bundle import BundleWriter
from .collect_tier1 import _read

_NAME = re.compile(r"^[A-Za-z0-9@._/-]{1,160}$")
_VERSION = re.compile(r"^[0-9A-Za-z._+-]{1,80}$")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,100}$")


def _json(source: Path, root: Path) -> dict[str, Any]:
    if not source.is_file() or source.is_symlink():
        return {}
    try:
        value = json.loads(_read(source, root))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def _toml(source: Path, root: Path) -> dict[str, Any]:
    if not source.is_file() or source.is_symlink():
        return {}
    try:
        value = tomllib.loads(_read(source, root).decode("utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def _names(value: Any) -> list[str]:
    keys = value.keys() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return sorted({item for item in keys if isinstance(item, str) and _NAME.fullmatch(item)}, key=str.casefold)


def _safe_url(raw: Any) -> str | None:
    if not isinstance(raw, str) or len(raw) > 2048:
        return None
    if re.fullmatch(r"[^@\s]+@[^:\s]+:[^?#\s]+", raw):
        _user, host_path = raw.split("@", 1)
        host, path = host_path.split(":", 1)
        return f"ssh://{host}/{path}" if _NAME.fullmatch(host) and _NAME.fullmatch(path) else None
    try:
        value = urlsplit(raw)
        if value.scheme not in {"http", "https", "ssh", "git"} or not value.hostname:
            return None
        host = value.hostname
        path = value.path
        if not _NAME.fullmatch(host) or not re.fullmatch(r"/[A-Za-z0-9@._/%+-]*", path):
            return None
        return f"{value.scheme}://{host}{(':' + str(value.port)) if value.port else ''}{path}"
    except ValueError:
        return None


def _program(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    name = ntpath.basename(raw.replace("/", "\\"))
    return name if _NAME.fullmatch(name) else None


def _git(skill: Path) -> tuple[bool, str | None, str | None]:
    if not (skill / ".git").exists():
        return False, None, None
    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(("git", "-C", str(skill), *args), capture_output=True,
                                    text=True, timeout=5, check=False, stdin=subprocess.DEVNULL)
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    head = run("rev-parse", "HEAD")
    if head is not None and not re.fullmatch(r"[a-fA-F0-9]{40,64}", head):
        head = None
    return True, _safe_url(run("config", "--get", "remote.origin.url")), head


def _size(folder: Path) -> int:
    total = 0
    for current, directories, files in os.walk(folder, followlinks=False):
        parent = Path(current)
        directories[:] = [name for name in directories if name != ".git" and not (parent / name).is_symlink()]
        for name in files:
            source = parent / name
            if not source.is_symlink():
                try:
                    total += source.stat().st_size
                except OSError:
                    pass
    return total


def _cc_skills(home: Path) -> list[dict[str, Any]]:
    root = home / ".cc-switch" / "skills"
    if not root.is_dir() or root.is_symlink():
        return []
    result = []
    for skill in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if not skill.is_dir() or skill.is_symlink() or not _NAME.fullmatch(skill.name):
            continue
        is_git, remote, head = _git(skill)
        result.append({"name": skill.name, "git": is_git, "remote": remote,
                       "head": head, "bytes": _size(skill)})
    return result


def _claude_plugins(root: Path) -> list[dict[str, Any]]:
    source = _json(root / "plugins" / "installed_plugins.json", root)
    raw = source.get("plugins", {})
    result = []
    if isinstance(raw, dict):
        for name, details in raw.items():
            if not isinstance(name, str) or not _NAME.fullmatch(name):
                continue
            records = details if isinstance(details, list) else [details]
            for item in records:
                if not isinstance(item, dict):
                    continue
                version = item.get("version")
                result.append({"name": name,
                               "version": version if isinstance(version, str) and _VERSION.fullmatch(version) else None,
                               "source": _safe_url(item.get("source") or item.get("gitUrl"))})
    return result


def reinstall_inventory(*, home: Path, environ: Mapping[str, str] | None = None,
                        agents: frozenset[str] = frozenset({"claude", "codex"}),
                        instances: Mapping[str, Path] | None = None) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    claude_root = Path(env.get("CLAUDE_CONFIG_DIR", str(home / ".claude")))
    codex_root = Path(env.get("CODEX_HOME", str(home / ".codex")))
    result: dict[str, Any] = {"cc_switch_skills": [], "claude_skills_link_to_cc_switch": False,
                              "claude_enabled_plugins": [], "claude_marketplaces": [],
                              "claude_installed_plugins": [], "codex_mcp_servers": [],
                              "codex_plugins": [], "codex_marketplaces": [],
                              "codex_hooks_present": False, "codex_notify_present": False,
                              "workbuddy": {}}
    if "claude" in agents:
        result["cc_switch_skills"] = _cc_skills(home)
        result["claude_skills_link_to_cc_switch"] = (claude_root / "skills").is_symlink()
        settings = _json(claude_root / "settings.json", claude_root)
        result["claude_enabled_plugins"] = _names(settings.get("enabledPlugins"))
        result["claude_marketplaces"] = _names(settings.get("extraKnownMarketplaces"))
        result["claude_installed_plugins"] = _claude_plugins(claude_root)
    if "codex" in agents:
        config = _toml(codex_root / "config.toml", codex_root)
        servers = config.get("mcp_servers", {})
        if isinstance(servers, dict):
            for name, entry in servers.items():
                if not isinstance(name, str) or not _NAME.fullmatch(name) or not isinstance(entry, dict):
                    continue
                command = entry.get("command")
                url = _safe_url(entry.get("url"))
                transport = entry.get("transport") or entry.get("type")
                if not isinstance(transport, str) or transport not in {"stdio", "http", "sse"}:
                    transport = "http" if url else "stdio" if isinstance(command, str) else "unknown"
                arguments = entry.get("args")
                variables = entry.get("env")
                result["codex_mcp_servers"].append({
                    "name": name, "transport": transport,
                    "program": _program(command),
                    "url": url, "args_count": len(arguments) if isinstance(arguments, list) else 0,
                    "env_keys": sorted(key for key in variables if isinstance(key, str) and _ENV.fullmatch(key))
                    if isinstance(variables, dict) else [],
                })
        result["codex_plugins"] = _names(config.get("plugins"))
        result["codex_marketplaces"] = _names(config.get("marketplaces"))
        result["codex_hooks_present"] = "hooks" in config
        result["codex_notify_present"] = "notify" in config
    for instance in ("workbuddy", "workbuddy-ai"):
        if instance in agents:
            root = (instances or {}).get(instance, home / f".{instance}")
            settings = _json(root / "settings.json", root)
            result["workbuddy"][instance] = {
                "enabled_plugins": _names(settings.get("enabledPlugins")),
                "sandbox_present": "sandbox" in settings,
                "auto_launch_present": "autoLaunchDesired" in settings,
            }
    return result


def add_reinstall_reports(writer: BundleWriter, inventory: dict[str, Any]) -> None:
    raw = json.dumps(inventory, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    if len(raw.encode("utf-8")) > 1_000_000:
        raise ValueError("reinstall report exceeds 1 MB")
    writer.add_report("reinstall.json", raw)
    lines = ["# 重装清单", "", "第三方技能、插件和 MCP 仅记录元数据；请在新机器上重新安装和授权。", ""]
    lines += [f"- CC Switch skills：{len(inventory['cc_switch_skills'])} 个。",
              f"- Claude 已启用插件：{len(inventory['claude_enabled_plugins'])} 个。",
              f"- Codex MCP 服务器：{len(inventory['codex_mcp_servers'])} 个。",
              "- WorkBuddy：按已批准分档手动恢复文本，插件重新安装。", ""]
    for skill in inventory["cc_switch_skills"]:
        lines.append(f"- CC Switch skill `{skill['name']}`：{skill['bytes']} B；来源 {skill['remote'] or '未记录'}；commit {skill['head'] or '未记录'}。")
    for label, key in (("Claude 插件", "claude_enabled_plugins"), ("Claude marketplace", "claude_marketplaces"),
                       ("Codex 插件", "codex_plugins"), ("Codex marketplace", "codex_marketplaces")):
        lines.extend(f"- {label} `{name}`：在新机器重新安装。" for name in inventory[key])
    for server in inventory["codex_mcp_servers"]:
        lines.append(f"- MCP `{server['name']}`：{server['transport']}，程序 {server['program'] or '未记录'}，端点 {server['url'] or '未记录'}，参数 {server['args_count']} 个；环境变量名：{', '.join(server['env_keys']) or '无'}。")
    for instance, settings in inventory["workbuddy"].items():
        lines.extend(f"- {instance} 插件 `{name}`：在新机器重新安装。" for name in settings["enabled_plugins"])
    writer.add_report("reinstall.md", "\n".join(lines))
