"""Produce a value-free checklist for credentials that must be set up again."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from typing import Mapping
from urllib.parse import urlsplit

from .bundle import BundleWriter
from .collect_reinstall import _ENV, _json, _toml


_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


def _git_credential_keys() -> list[str]:
    try:
        result = subprocess.run(("git", "config", "--global", "--name-only", "--get-regexp", r"^credential\."),
                                capture_output=True, text=True, timeout=5, check=False, stdin=subprocess.DEVNULL)
        return result.stdout.splitlines()[:1000] if result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        return []


def _credential_hosts(keys: list[str]) -> list[str]:
    hosts: set[str] = set()
    for key in keys:
        if not key.startswith("credential."):
            continue
        if key.casefold() in {"credential.helper", "credential.usehttppath", "credential.interactive"}:
            continue
        tail = key[len("credential."):]
        if "." not in tail:
            continue
        section = tail.rsplit(".", 1)[0]
        try:
            host = urlsplit(section).hostname if "://" in section else section
        except ValueError:
            continue
        if host and _HOST.fullmatch(host):
            hosts.add(host.lower())
    return sorted(hosts)


def login_checklist(*, home: Path, environ: Mapping[str, str] | None = None,
                    git_keys: list[str] | None = None,
                    agents: frozenset[str] = frozenset({"claude", "codex", "workbuddy", "workbuddy-ai"}),
                    mcp_hosts: list[str] | None = None) -> str:
    env = os.environ if environ is None else environ
    lines = ["# 新机器登录与密钥清单", "", "此报告不包含密钥、令牌、Cookie 或登录文件；请从原服务或你自己的安全存储重新取得。", ""]
    if "claude" in agents:
        root = Path(env.get("CLAUDE_CONFIG_DIR", str(home / ".claude")))
        if root.exists() or (home / ".claude.json").exists():
            lines.append("- Claude：在新机器登录账户，按产品登录界面完成。")
        settings = _json(root / "settings.json", root)
        variables = settings.get("env", {})
        if isinstance(variables, dict):
            for key in sorted(variables):
                if isinstance(key, str) and _ENV.fullmatch(key):
                    lines.append(f"- Claude 环境变量 `{key}`：从原服务控制台或个人安全存储重新填写。")
    if "codex" in agents:
        root = Path(env.get("CODEX_HOME", str(home / ".codex")))
        if root.exists():
            lines.append("- Codex：在新机器登录账户，按产品登录界面完成。")
        config = _toml(root / "config.toml", root)
        shell = config.get("shell_environment_policy", {})
        variables = shell.get("set", {}) if isinstance(shell, dict) else {}
        if isinstance(variables, dict):
            for key in sorted(variables):
                if isinstance(key, str) and _ENV.fullmatch(key):
                    lines.append(f"- Codex 环境变量 `{key}`：从原服务控制台或个人安全存储重新填写。")
    if (home / ".cc-switch").exists() and "claude" in agents:
        lines.append("- CC Switch 服务配置：在新机器重新添加服务提供方，并从各服务控制台取得凭据；本备份不含其数据库或设置。")
    credential_keys = _git_credential_keys() if git_keys is None else git_keys
    if credential_keys or (home / ".git-credentials").exists():
        lines.append("- Git 凭据管理器：在新机器重新认证；不要复制凭据文件。")
        for host in _credential_hosts(credential_keys):
            lines.append(f"- Git 主机 `{host}`：到该主机账户安全设置重新授权。")
    ssh = home / ".ssh"
    if ssh.is_dir() and not ssh.is_symlink() and any(
        path.is_file() and not path.is_symlink() and
        (path.name in {"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"} or path.suffix == ".pem")
        for path in ssh.iterdir()
    ):
        lines.append("- SSH 私钥：由你自行通过安全方式转移，备份文件不包含私钥；在新机器核对权限和公钥登记。")
    for host in sorted(set(mcp_hosts or [])):
        if isinstance(host, str) and _HOST.fullmatch(host):
            lines.append(f"- MCP OAuth `{host}`：在新机器打开对应服务重新授权。")
    if any((home / f".{name}").exists() for name in ("workbuddy", "workbuddy-ai") if name in agents):
        lines.append("- WorkBuddy：在新机器登录相应应用；账户与连接器信息不在备份文件中。")
    return "\n".join(lines) + "\n"


def add_login_report(writer: BundleWriter, checklist: str) -> None:
    if len(checklist.encode("utf-8")) > 1_000_000:
        raise ValueError("login checklist exceeds 1 MB")
    writer.add_report("login-checklist.md", checklist)
