"""Prepare an offline backup in memory; publish it only on explicit apply."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from .bundle import BundleError, BundleWriter, content_id, validate_bundle
from .collect_login import add_login_report, login_checklist
from .collect_projects import ProjectResult, collect_projects
from .collect_records import software_inventory
from .collect_reinstall import add_reinstall_reports, reinstall_inventory
from .collect_tier1 import CollectionResult, collect_tier1
from .collect_workbuddy import collect_workbuddy
from .config import MachineConfig
from .guided import AGENT_LABELS, KIND_LABELS, REASON_LABELS
from .paths import norm


AGENTS = frozenset({"claude", "codex", "workbuddy", "workbuddy-ai"})


def agent_roots(home: Path, config: MachineConfig, env: Mapping[str, str]) -> dict[str, Path]:
    return {"claude": Path(env.get("CLAUDE_CONFIG_DIR", str(home / ".claude"))),
            "codex": Path(env.get("CODEX_HOME", str(home / ".codex"))),
            **{name: config.instances.get(name, home / f".{name}") for name in ("workbuddy", "workbuddy-ai")}}


def validate_output(out: Path, *, roots: tuple[Path, ...], projects: tuple[Path, ...]) -> Path:
    if not out.is_dir() or out.is_symlink():
        raise ValueError("output must be an existing directory without a symbolic link")
    target = out.resolve()
    for boundary in (*roots, *projects):
        if target.is_relative_to(boundary.resolve()):
            raise ValueError("output may not be inside an agent root or core project")
    return target


def _prefix(name: str) -> str:
    if (not name or len(name) > 60 or name in {".", ".."} or name != name.strip()
            or name.endswith(".") or re.search(r'[<>:"/\\|?*\x00-\x1f\x7f]', name)):
        raise ValueError("invalid bundle filename prefix")
    return name


@dataclass
class BackupPlan:
    writer: BundleWriter
    selected_agents: frozenset[str]
    roots: tuple[Path, ...]
    core_projects: tuple[Path, ...]
    collections: tuple[CollectionResult, ...]
    project_result: ProjectResult
    exclusions: list[dict[str, Any]]
    warnings: list[dict[str, Any]]

    def verify_sources_unchanged(self) -> bool:
        return all(result.verify_sources_unchanged() for result in self.collections)

    def preview(self) -> dict[str, Any]:
        self.check_privacy()
        return {"mode": "preview", "destination": str(self.writer.destination),
                "agents": sorted(self.selected_agents), "entries": len(self.writer.entries),
                "by_agent": dict(Counter(item["agent"] for item in self.writer.entries)),
                "by_tier": dict(Counter(str(item["tier"]) for item in self.writer.entries)),
                "projects": len(self.project_result.projects),
                "flags": [{"logical_path": item["logical_path"], "flags": item["flags"]}
                          for item in self.writer.entries if item["flags"]],
                "exclusions": self.exclusions, "warnings": self.warnings,
                "content_id": content_id(self.writer.entries)}

    def check_privacy(self) -> None:
        self.writer.check_privacy(projects=self.project_result.projects,
                                  exclusions=self.exclusions, warnings=self.warnings)


def _summary(writer: BundleWriter, projects: ProjectResult, exclusions: list[dict[str, Any]],
             warnings: list[dict[str, Any]], software: dict[str, Any]) -> str:
    lines = ["# AI 助手备份摘要", "", "## 已纳入", ""]
    counts = Counter((item["agent"], item["kind"]) for item in writer.entries if item["kind"] != "report")
    lines.extend(f"- {AGENT_LABELS[agent]} {KIND_LABELS[kind]}：{count} 个文件。" for (agent, kind), count in sorted(counts.items()))
    lines += [f"- 工作文件夹 {len(projects.projects)} 个；这台电脑上找不到的登记文件夹 {projects.dead_registered} 个。", "",
              "## 未备份清单（请核对）", "",
              "- 登录文件、密钥、Cookie、会话正文／数据库、缓存和运行目录不进入此包。",
              "- 第三方技能、插件和 MCP 按 reinstall.md 重装；登录项按 login-checklist.md 重新填写。"]
    lines.extend(f"- **{REASON_LABELS.get(item['reason'], '需要人工核对')}**：{item.get('source_path', item['logical_path'])}" for item in exclusions)
    if not exclusions:
        lines.append("- 本次未发现额外排除的已选文件。")
    lines += ["", "## 规则重复与绝对路径", ""]
    for item in writer.entries:
        for flag in item["flags"]:
            if flag.startswith("duplicate_lines:"):
                duplicate, total = map(int, flag.split(":", 1)[1].split("/"))
                lines.append(f"- {item['logical_path']}：非空行 {total}，唯一 {total - duplicate}。")
            elif flag.startswith("abs_path:") and flag != "abs_path:0":
                lines.append(f"- {item['logical_path']}：含绝对路径标记 {flag.split(':')[1]} 处，请在新机器核对。")
    lines += ["", "## 提醒", ""]
    lines.extend(f"- {warning['code']}：{warning['message']}" for warning in warnings)
    version_names = {"codex_desktop_version": "Codex 桌面版", "cc_switch_version": "CC Switch",
                     "claude_desktop_claude_code_versions": "Claude 内置命令工具"}
    lines.extend(f"- 软件版本未核实：{version_names.get(item, '一项本机软件')}" for item in software.get("unverified", []))
    if any(item["agent"] in {"workbuddy", "workbuddy-ai"} for item in writer.entries):
        lines.append("- WorkBuddy 文本为手动还原候选，自动加载尚未验证。")
    lines += ["",
              "## 如何在新机器还原", "",
              "保留完整备份文件，先在新电脑安装并启动对应助手一次，再双击「恢复」。也可以把备份文件拖到 Windows 的「恢复」图标上。",
              "检查选择后确认恢复。已有不同内容会保留；需要回到原状时，再次打开「恢复」选择撤销。WorkBuddy 文本与安全设置默认跳过，需要你明确同意。真实跨机和新手试用尚未验收。", "",
              "<details><summary>详细信息（技术支持）</summary>", "",
              "专家入口为 `python scripts/machine.py preflight --bundle <备份文件>`，核对后执行 `python scripts/machine.py restore --bundle <备份文件> --apply`。",
              "核对用 verify，撤销用 undo。真实目标写入需明确授权，并先在净室演练。", "", "</details>", ""]
    return "\n".join(lines)


def prepare_backup(*, home: Path, config: MachineConfig, out: Path, name: str = "machine-bundle",
                   agents: frozenset[str] | None = None, environ: Mapping[str, str] | None = None,
                   os_name: str | None = None, now: datetime | None = None,
                   software: dict[str, Any] | None = None, git_keys: list[str] | None = None) -> BackupPlan:
    env = os.environ if environ is None else environ
    system = os_name or platform.system().lower()
    roots = agent_roots(home, config, env)
    selected = agents if agents is not None else frozenset(name for name, root in roots.items() if root.is_dir())
    if not selected or selected - AGENTS:
        raise ValueError("select at least one supported agent")
    output = validate_output(out, roots=tuple(roots.values()), projects=config.core_projects)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")
    destination = output / f"{_prefix(name)}-{timestamp}.zip"
    writer = BundleWriter(destination, source={"os": system, "arch": platform.machine(), "home": norm(home, system)})
    tier1 = collect_tier1(writer, home=home, config=config, environ=env, agents=selected, os_name=system)
    projects = collect_projects(writer, home=home, config=config, environ=env, agents=selected, os_name=system)
    workbuddy = collect_workbuddy(writer, home=home, config=config, environ=env, agents=selected, os_name=system)
    collections = (tier1, projects, workbuddy)
    exclusions = list({(item.get('source_path',item['logical_path']),item['reason']):item
                       for result in collections for item in result.exclusions}.values())
    warnings = [item for result in collections for item in result.warnings]
    inventory = reinstall_inventory(home=home, environ=env, agents=selected, instances=config.instances)
    add_reinstall_reports(writer, inventory)
    hosts = [urlsplit(server["url"]).hostname for server in inventory["codex_mcp_servers"] if server["url"]]
    add_login_report(writer, login_checklist(home=home, environ=env, agents=selected, git_keys=git_keys,
                                            mcp_hosts=[host for host in hosts if host]))
    software_report = software if software is not None else software_inventory(home=home, process_names=config.running_process_names)
    writer.add_report("software.json", json.dumps(software_report, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    writer.add_report("summary.md", _summary(writer, projects, exclusions, warnings, software_report))
    plan = BackupPlan(writer, selected, tuple(roots.values()), config.core_projects, collections, projects, exclusions, warnings)
    plan.check_privacy()
    if not plan.verify_sources_unchanged():
        raise BundleError("a selected source changed during collection")
    return plan


def apply_backup(plan: BackupPlan) -> dict[str, Any]:
    plan.check_privacy()
    validate_output(plan.writer.destination.parent, roots=plan.roots, projects=plan.core_projects)
    if not plan.verify_sources_unchanged():
        raise BundleError("a selected source changed after preview")
    manifest = plan.writer.finalize(projects=plan.project_result.projects, exclusions=plan.exclusions, warnings=plan.warnings)
    validate_bundle(plan.writer.destination)
    digest = hashlib.sha256()
    with plan.writer.destination.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if not plan.verify_sources_unchanged():
        raise BundleError("a selected source changed while publishing; retain the zip for review")
    return {**plan.preview(), "mode": "applied", "sha256": digest.hexdigest(),
            "bytes": plan.writer.destination.stat().st_size, "content_id": manifest["content_id"]}
