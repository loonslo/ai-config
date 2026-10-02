"""First-time setup and additional-device onboarding wizard.

Distinguishes the first device (which must state the configuration source
address) from a device joining an existing source (which verifies that address
instead).  Device IDs are generated to avoid collisions, tools are detected,
and the user chooses between "shared rules + selected tool settings" and "shared
rules only".

Memory is off by default.  Running the wizard does not mean three devices are
already in sync; the output never claims that.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import platform
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from .config import DeviceConfig, validate as validate_device
from .environment import detect as detect_environment
from .utils import atomic_write, json_bytes

SCHEMA_VERSION = 1

#: Scope choices presented to the user.
SCOPE_RULES_ONLY = "rules_only"
SCOPE_RULES_AND_TOOLS = "rules_and_tools"
SCOPES = (SCOPE_RULES_ONLY, SCOPE_RULES_AND_TOOLS)


class SetupCancelled(RuntimeError):
    """The user cancelled: nothing half-applied may remain."""


class SetupError(RuntimeError):
    """Setup cannot continue; the reason is user-actionable."""


def stable_device_id(*, system: str | None = None, hostname: str | None = None, existing: set[str] | None = None) -> str:
    """Generate a stable, collision-free device id.

    The id is derived from the platform and host so it stays the same across
    runs, then disambiguated with a short hash whenever it would collide with an
    already recorded device.
    """
    resolved_system = (system or platform.system()).casefold()
    prefix = "mac" if resolved_system == "darwin" else "windows" if resolved_system == "windows" else re.sub(r"[^a-z0-9]+", "", resolved_system) or "device"
    host = (hostname or platform.node()).casefold()
    slug = re.sub(r"[^a-z0-9_-]+", "-", host).strip("-") or "local"
    candidate = f"{prefix}-{slug}"[:48].rstrip("-")
    taken = existing or set()
    if candidate not in taken:
        return candidate
    suffix = hashlib.sha256(f"{resolved_system}:{host}".encode("utf-8")).hexdigest()[:6]
    disambiguated = f"{candidate[:41].rstrip('-')}-{suffix}"
    counter = 1
    while disambiguated in taken:
        counter += 1
        disambiguated = f"{candidate[:39].rstrip('-')}-{suffix}{counter}"
    return disambiguated


def registered_devices(memory_repo: Path) -> set[str]:
    """Read known device ids without creating anything."""
    devices: set[str] = set()
    receipts = memory_repo / "receipts"
    if receipts.is_dir():
        devices.update(path.stem for path in receipts.glob("*.json"))
    registry = memory_repo / "registry" / "devices.json"
    if registry.exists():
        try:
            data = json.loads(registry.read_text(encoding="utf-8"))
            devices.update(data.get("devices", {}).keys())
        except (OSError, ValueError):
            pass
    return {device for device in devices if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", device)}


def plan_device(
    *,
    device_id: str | None = None,
    state_dir: Path,
    memory_repo: Path,
    tools: list[str],
    scope: str,
    remote_url: str | None,
    tool_roots: Mapping[str, str] | None = None,
    codex_keys: list[str] | None = None,
    claude_keys: list[str] | None = None,
    memories: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the device configuration document without writing it."""
    if scope not in SCOPES:
        raise SetupError(f"未知的共享范围：{scope}")
    if not tools:
        raise SetupError("至少需要选择一个工具，或者明确选择仅公共规则。")
    from .agents import LEGACY_INSTANCES, profile_for_instance

    roots = dict(tool_roots or {})
    resolved_tools = sorted(set(tools))
    for tool in resolved_tools:
        profile = profile_for_instance(tool)
        if tool not in LEGACY_INSTANCES and (profile is None or not profile.writable):
            raise SetupError(f"不支持的工具：{tool}")
    config: dict[str, Any] = {
        "device": device_id or stable_device_id(),
        "state_dir": str(state_dir),
        "memory_repo": str(memory_repo),
        "codex_keys": [],
        "claude_keys": [],
        "codex_overrides": {},
        "claude_overrides": {},
        "tool_versions": {},
        "additional_sources": [],
        "memories": memories or [],
        "projects": {},
    }
    agents: dict[str, Any] = {}
    for tool in resolved_tools:
        root = roots.get(tool)
        if not root:
            raise SetupError(f"缺少 {tool} 的配置目录。")
        if tool in LEGACY_INSTANCES:
            config[tool] = root
        else:
            # Agents other than Codex/Claude are declared under ``agents``; they
            # only ever receive the managed rules entry from the registry.
            agents[tool] = {"root": root}
    if agents:
        config["agents"] = agents
    if scope == SCOPE_RULES_AND_TOOLS:
        # Tool settings are only ever managed for Codex and Claude.
        if "codex" in resolved_tools:
            config["codex_keys"] = list(codex_keys or [])
        if "claude" in resolved_tools:
            config["claude_keys"] = list(claude_keys or [])
    if remote_url:
        config["remote_url"] = remote_url
        config["remote_identity"] = identity_of(remote_url)
    # Memory stays off unless the caller explicitly supplied mappings.
    if not config["memories"] and "codex" in resolved_tools and scope == SCOPE_RULES_AND_TOOLS:
        pass
    validate_device({key: value for key, value in config.items() if not key.startswith("remote_")})
    return config


def identity_of(url: str) -> str:
    """A credential-free identity for a remote URL, safe to display."""
    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(url)
    if parsed.scheme and parsed.netloc and parsed.hostname:
        netloc = parsed.hostname + (f":{parsed.port}" if parsed.port else "")
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    return url.split("@", 1)[-1]


def describe_detected(environment: Mapping[str, Any]) -> list[str]:
    """Show the user what was detected and what will be applied."""
    lines = [f"系统：{environment.get('system')}"]
    for tool in environment.get("tools", []):
        state = "已安装" if tool.get("installed") else "未发现"
        lines.append(f"  {tool['tool']}：{state}（目录 {tool['root']}，来源：{tool['root_origin']}）")
    dependencies = environment.get("dependencies", {})
    lines.append(f"Python：{dependencies.get('python', {}).get('version', '未知')}")
    lines.append(f"Git：{'可用' if dependencies.get('git', {}).get('ok') else '未找到'}")
    return lines


def describe_plan(config: Mapping[str, Any]) -> list[str]:
    """Show the values that are about to be written, before writing them."""
    lines = [
        f"设备 ID：{config['device']}",
        f"配置源状态目录：{config['state_dir']}",
        f"共享配置源：{config.get('remote_identity') or '（未设置，本机先作为第一台设备）'}",
        f"共享记忆仓库：{config['memory_repo']}",
    ]
    if config.get("config_repo"):
        lines.append(f"配置库（各 agent 的规则来源）：{config['config_repo']}")
    from .agents import display_name

    for tool in ("codex", "claude"):
        if config.get(tool):
            lines.append(f"{tool} 配置目录：{config[tool]}")
    for instance, spec in sorted((config.get("agents") or {}).items()):
        lines.append(f"{display_name(instance)} 配置目录：{spec.get('root')}（只接管规则入口）")
    lines.append("受管字段：" + ", ".join(f"{tool}={config.get(f'{tool}_keys') or []}" for tool in ("codex", "claude") if config.get(tool)))
    lines.append("记忆同步：" + ("已启用" if config.get("memories") else "未启用（默认）"))
    return lines


def write_config(config: Mapping[str, Any], target: Path, *, backup: bool = True) -> dict[str, Any]:
    """Write device.json, preserving any existing file first."""
    backup_path: Path | None = None
    if target.exists() and backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = target.with_name(f"{target.name}.bak-{stamp}")
        backup_path.write_bytes(target.read_bytes())
    payload = {key: value for key, value in config.items()}
    atomic_write(target, json_bytes(payload))
    return {"config_path": str(target), "backup": str(backup_path) if backup_path else None}


def join_existing(
    *,
    remote_url: str,
    expected_identity: str | None,
    tools: list[str],
    tool_roots: Mapping[str, str],
    state_dir: Path,
    memory_repo: Path,
    registered: set[str] | None = None,
    scope: str = SCOPE_RULES_ONLY,
) -> dict[str, Any]:
    """Prepare a second or third device joining an existing source.

    Shared field selection is reused rather than re-asked; only local facts such
    as paths are re-detected.
    """
    identity = identity_of(remote_url)
    if expected_identity and identity != expected_identity:
        raise SetupError(f"配置源身份不匹配：期望 {expected_identity}，实际 {identity}。已停止，未写入任何配置。")
    if not remote_url:
        raise SetupError("加入已有配置源需要提供配置源地址。")
    known = registered or set()
    device_id = stable_device_id(existing=known)
    config = plan_device(
        device_id=device_id,
        state_dir=state_dir,
        memory_repo=memory_repo,
        tools=tools,
        scope=scope,
        remote_url=remote_url,
        tool_roots=tool_roots,
    )
    return {"config": config, "identity": identity, "device_id": device_id, "joined": True}


def run_wizard(
    *,
    ask: Callable[[str], str],
    state_dir: Path,
    memory_repo: Path,
    environment: Mapping[str, Any],
    first_device: bool,
    target: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Minimal Chinese interactive wizard.

    Every answer is validated before anything is written, and cancellation
    raises without leaving a partially applied configuration.
    """
    answers: dict[str, str] = {}

    def prompt(key: str, question: str, default: str | None = None) -> str:
        suffix = f"（默认 {default}）" if default else ""
        reply = ask(f"{question}{suffix}: ").strip()
        value = reply or (default or "")
        if not value:
            raise SetupCancelled("已取消：没有填写必要信息，未写入任何配置。")
        answers[key] = value
        return value

    installed = [tool["tool"] for tool in environment.get("tools", []) if tool.get("installed")]
    if not installed:
        raise SetupError("未检测到任何已安装的工具配置目录，请先安装并启动目标工具。")

    remote_identity = None
    if first_device:
        remote_url = prompt("remote_url", "请输入共享配置源地址（例如 Git 远端地址）")
        remote_identity = identity_of(remote_url)
    else:
        remote_url = prompt("remote_url", "请输入已有配置源地址以加入")

    scope_answer = prompt("scope", "共享范围：1=公共规则＋选定工具设置，2=仅公共规则", default="2")
    scope = SCOPE_RULES_AND_TOOLS if scope_answer.strip() in {"1", SCOPE_RULES_AND_TOOLS} else SCOPE_RULES_ONLY

    chosen_tools = list(installed)
    roots = {tool["tool"]: tool["root"] for tool in environment.get("tools", []) if tool.get("installed")}
    config = plan_device(
        state_dir=state_dir,
        memory_repo=memory_repo,
        tools=chosen_tools,
        scope=scope,
        remote_url=remote_url,
        tool_roots=roots,
        codex_keys=[] if scope == SCOPE_RULES_ONLY else ["web_search"],
        claude_keys=[] if scope == SCOPE_RULES_ONLY else [],
    )
    preview = {"detected": describe_detected(environment), "plan": describe_plan(config), "answers": dict(answers)}
    if dry_run:
        return {"status": "preview", "ready": False, "config": config, **preview}
    written = write_config(config, target)
    return {"status": "configured", "ready": True, "config": config, "written": written, **preview, "note": "本机配置已写入；这不代表其他设备已经同步。"}
