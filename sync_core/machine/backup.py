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
import uuid
from typing import Any, Mapping
from urllib.parse import urlsplit

from .bundle import BundleError, BundleWriter, content_id, validate_bundle
from .collect_login import add_login_report, login_checklist
from .collect_projects import ProjectResult, collect_projects
from .collect_records import software_inventory
from .collect_reinstall import add_reinstall_reports, reinstall_inventory
from .collect_tier1 import CollectionResult, collect_tier1
from .collect_workbuddy import collect_workbuddy
from .collect_classified import collect_classified
from .collect_env import collect_environment
from .collect_desktop_skills import collect_desktop_skills
from .collect_skills import collect_skills, skills_report, skills_markdown
from .source_roots import desktop_root
from .config import MachineConfig, excluded_path
from .coverage import Ledger, Limits, SourceRoot, walk_root
from .collect_tier1 import project_id
from .guided import AGENT_LABELS, KIND_LABELS, REASON_LABELS
from .paths import norm
from .groups import selected_groups, group_counts
from .history import HistoryPlan, HistoryLimits, prepare_history, write_history, publish_files


AGENTS = frozenset({"claude", "codex", "workbuddy", "workbuddy-ai", "shared"})


def agent_roots(home: Path, config: MachineConfig, env: Mapping[str, str]) -> dict[str, Path]:
    return {"claude": Path(env.get("CLAUDE_CONFIG_DIR", str(home / ".claude"))),
            "codex": Path(env.get("CODEX_HOME", str(home / ".codex"))),
            "shared": home / ".agents",
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
    coverage: dict[str, Any] | None = None
    history: HistoryPlan | None = None

    def verify_sources_unchanged(self) -> bool:
        return all(result.verify_sources_unchanged() for result in self.collections) and (self.history is None or self.history.verify_sources_unchanged())

    def preview(self) -> dict[str, Any]:
        self.check_privacy()
        return {"mode": "preview", "destination": str(self.writer.destination),
                "agents": sorted(self.selected_agents), "entries": len(self.writer.entries),
                "by_agent": dict(Counter(item["agent"] for item in self.writer.entries)),
                "by_tier": dict(Counter(str(item["tier"]) for item in self.writer.entries)),
                "by_group": {**group_counts(self.writer.entries), **({'history': {'files': len(self.history.sources), 'bytes': self.history.report()['bytes']}} if self.history else {})},
                "history": {**self.history.report(), 'packages': self.history.references(self.writer.destination)} if self.history else None,
                "skills": json.loads(self.writer._files.get('reports/skills.json',b'{"summary":{}}'))['summary'],
                "projects": len(self.project_result.projects),
                "flags": [{"logical_path": item["logical_path"], "flags": item["flags"]}
                          for item in self.writer.entries if item["flags"]],
                "exclusions": self.exclusions, "warnings": self.warnings,
                "content_id": content_id(self.writer.entries),
                "flagged": {"policy": self.writer.flagged_policy, "count": len(self.writer.flagged),
                            "items": self.writer.flagged},
                "oversize": self.writer.oversize,
                "coverage": {"unclassified": self.coverage["totals"]["unclassified"],
                             "samples": [f"{root['id']}/{path}" for root in self.coverage['roots'] for path in root['unclassified']['samples']][:20],
                             "roots": len(self.coverage["roots"]), "complete": self.coverage["totals"]["complete"]}
                if self.coverage is not None else None}

    def check_privacy(self) -> None:
        self.writer.check_privacy(projects=self.project_result.projects,
                                  exclusions=self.exclusions, warnings=self.warnings)


def _coverage(*, home: Path, roots: dict[str, Path], selected: frozenset[str], config: MachineConfig,
              env: Mapping[str, str], system: str, writer: BundleWriter,
              collections: tuple[CollectionResult, ...], history: HistoryPlan | None = None) -> dict[str, Any]:
    ledger = Ledger()
    boundaries = [("claude_home" if agent == "claude" else "codex_home" if agent == "codex"
                   else "agents_home" if agent == "shared" else agent.replace("-", "_"), agent, roots[agent]) for agent in sorted(selected)]
    if "claude" in selected:
        boundaries.append(("claude_json", "claude", home / ".claude.json"))
        desktop = desktop_root(home, env)
        if desktop is not None:
            boundaries.append(('claude_desktop', 'claude', desktop))
    boundaries.extend((f"project:{project_id(p, system)}", "project", p) for p in config.core_projects)
    logical = {entry["logical_path"] for entry in writer.entries if entry["kind"] != "report"}
    if history is not None:
        logical.update(f'{s.agent}:history/{s.relative}' for s in history.sources)
    origins = {path: origin for result in collections for path, origin in result.coverage_origins.items()}
    source_logical = {path: name for result in collections for path, name in result.coverage_logical.items()}
    approved_links = {path: target for result in collections for path, target in result.approved_links.items()}
    observed_roots: set[str] = set()
    for id, agent, base in boundaries:
        if id in observed_roots:
            continue
        observed_roots.add(id)
        source_root = SourceRoot(id, agent, "main", lambda h, e, p=base: p)
        for _ in walk_root(source_root, home=home, environ=env,
                           excluded=lambda p, b=base: excluded_path(p, config=config, home=home, os_name=system, boundary=b),
                           ledger=ledger, limits=Limits(), origins=origins, approved_links=approved_links):
            pass
        for seen_root, relative in tuple(ledger._seen):
            if seen_root != id:
                continue
            physical = base/relative
            for link, target in approved_links.items():
                if physical.is_relative_to(link):
                    physical = target/physical.relative_to(link)
                    break
            names = {f"{agent}:main/{relative}", f"{agent}:agent/{relative}", f"{id}/{relative}",
                     f'{agent}:history/{relative}'}
            if physical in source_logical:
                names.add(source_logical[physical])
            if agent == "project":
                names.update(f"{a}:project/{relative}" for a in ("workbuddy", "workbuddy-ai"))
            if names & logical:
                ledger.carried(id, relative, ledger._decisions[id, relative])
    for collection in collections:
        for root, reasons in collection.coverage_issues.items():
            for reason in sorted(reasons):
                ledger.issue(root,reason)
    report = ledger.report()
    report["fields"] = [item for result in collections for item in result.field_ledger.report()["fields"]]
    report["field_mode"] = "classification_only"
    return report

def _summary(writer: BundleWriter, projects: ProjectResult, exclusions: list[dict[str, Any]],
             warnings: list[dict[str, Any]], software: dict[str, Any]) -> str:
    lines = ["# AI 助手备份摘要", "", "## 已纳入", ""]
    counts = Counter((item["agent"], item["kind"]) for item in writer.entries if item["kind"] != "report")
    lines.extend(f"- {AGENT_LABELS[agent]} {KIND_LABELS[kind]}：{count} 个文件。" for (agent, kind), count in sorted(counts.items()))
    lines += [f"- 工作文件夹 {len(projects.projects)} 个；这台电脑上找不到的登记文件夹 {projects.dead_registered} 个。", "",
              "## 未备份清单（请核对）", "",
              "- 登录文件、密钥、Cookie、会话正文／数据库、缓存和运行目录不进入此包。",
              "- 已携带的第三方技能及来源见 skills.md；未携带的插件和服务连接工具按 reinstall.md 重装，登录项按 login-checklist.md 重新填写。"]
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
              "保留完整备份文件，先在新电脑安装并启动对应助手一次，再打开 AI Config 桌面客户端的「恢复」。选择备份 ZIP，也可以将它拖进客户端窗口。",
              "检查选择后确认恢复。已有不同内容会保留；需要回到原状时，在「恢复记录」选择一次恢复，检查后撤销。WorkBuddy 文本与安全设置默认跳过，需要你明确同意。真实跨机和新手试用尚未验收。", ""]
    return "\n".join(lines)


def prepare_backup(*, home: Path, config: MachineConfig, out: Path, name: str = "machine-bundle",
                   agents: frozenset[str] | None = None, environ: Mapping[str, str] | None = None,
                   os_name: str | None = None, now: datetime | None = None,
                   software: dict[str, Any] | None = None, git_keys: list[str] | None = None,
                   observe_coverage: bool = True, flagged_policy: str = "redact",
                   user_environment: Mapping[str, str | None] | None = None,
                   groups: frozenset[str] | None = None,
                   history_limits: HistoryLimits = HistoryLimits()) -> BackupPlan:
    env = os.environ if environ is None else environ
    system = os_name or platform.system().lower()
    roots = agent_roots(home, config, env)
    selected = agents if agents is not None else frozenset(name for name, root in roots.items() if root.is_dir())
    if not selected or selected - AGENTS:
        raise ValueError("select at least one supported agent")
    desktop = desktop_root(home, env) if 'claude' in selected else None
    output = validate_output(out, roots=tuple(roots.values()) + ((desktop,) if desktop else ()), projects=config.core_projects)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")
    destination = output / f"{_prefix(name)}-{timestamp}.zip"
    writer = BundleWriter(destination, source={"os": system, "arch": platform.machine(), "home": norm(home, system)},
                          flagged_policy=flagged_policy)
    writer.groups=selected_groups(groups)
    history = prepare_history({a: roots[a] for a in selected}, selected=True, policy=flagged_policy,
                              limits=history_limits, excluded=lambda p,r: excluded_path(p,config=config,home=home,os_name=system,boundary=r)) if 'history' in writer.groups else None
    tier1 = collect_tier1(writer, home=home, config=config, environ=env, agents=selected, os_name=system, collect_skills=False)
    projects = collect_projects(writer, home=home, config=config, environ=env, agents=selected, os_name=system)
    workbuddy = collect_workbuddy(writer, home=home, config=config, environ=env, agents=selected, os_name=system, collect_skills=False)
    classified = collect_classified(writer, home=home, config=config, environ=env, agents=selected, roots=roots, os_name=system, collect_skills=False)
    user_env = collect_environment(writer, home=home, config=config, os_name=system, table=user_environment)
    desktop_skills = collect_desktop_skills(writer,home=home,config=config,environ=env,agents=selected,os_name=system)
    skills = collect_skills(writer,home=home,config=config,roots=roots,agents=selected,os_name=system)
    collections = (tier1, projects, workbuddy, classified, user_env, desktop_skills, skills)
    coverage = _coverage(home=home, roots=roots, selected=selected, config=config, env=env,
                         system=system, writer=writer, collections=collections, history=history) if observe_coverage else None
    collected_exclusions = [item for result in collections for item in result.exclusions]
    exclusions = list({(item.get('source_path',item['logical_path']),item['reason']):item
                       for item in [*collected_exclusions, *writer.oversize]}.values())
    warnings = [item for result in collections for item in result.warnings]
    inventory = reinstall_inventory(home=home, environ=env, agents=selected, instances=config.instances)
    add_reinstall_reports(writer, inventory)
    hosts = [urlsplit(server["url"]).hostname for server in inventory["codex_mcp_servers"] if server["url"]]
    checklist = login_checklist(home=home, environ=env, agents=selected, git_keys=git_keys,
                               mcp_hosts=[host for host in hosts if host])
    checklist += ''.join(f'- 用户级环境变量 `{key}`：从原服务或个人安全存储重新填写。\n' for key in user_env.login_names)
    add_login_report(writer, checklist)
    software_report = software if software is not None else software_inventory(home=home, process_names=config.running_process_names)
    writer.add_report("software.json", json.dumps(software_report, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    writer.add_report('account-skills.json', json.dumps({'skills':desktop_skills.skills},ensure_ascii=False,sort_keys=True) + '\n')
    skill_report = skills_report([*skills.skills,*desktop_skills.skills])
    from .exports import account_member
    from .coverage import safe_name
    for entry in writer.entries:
        if entry['agent']=='claude' and entry['instance']=='desktop' and entry['kind']=='skills':
            account,name,_=account_member(entry['archive_path'])
            record=next(r for r in desktop_skills.skills if r['account']==account and r['name']==safe_name(name))
            entry['provenance_id']=record['id']
        if any(entry.get('provenance_id') in c['members'] for c in skill_report['copies'] if c['relation']=='diverged'):
            entry['flags'].append('diverged_copy')
    writer.add_report('skills.json',json.dumps(skill_report,ensure_ascii=False,sort_keys=True)+'\n')
    writer.add_report('skills.md',skills_markdown(skill_report))
    summary = _summary(writer, projects, exclusions, warnings, software_report)
    if skill_report['summary']['third_party']:
        summary+='\n## 第三方技能\n\n发现 '+str(skill_report['summary']['third_party'])+' 个技能；选择与携带情况、来源及未携带文件见 skills.md。\n'
    if skill_report['copies']:
        summary+='\n## 同名技能\n\n各份均分别保留，内容相同或不同见 skills.md。\n'
    if history is not None:
        writer.flagged.extend(history.flagged)
    writer.add_report("flagged.json", json.dumps({"policy": writer.flagged_policy, "items": writer.flagged},
                                                ensure_ascii=False, sort_keys=True) + "\n")
    if coverage is not None:
        writer.add_report("coverage.json", json.dumps(coverage, ensure_ascii=False, sort_keys=True) + "\n")
        if coverage["totals"]["unclassified"]:
            summary += "\n## 未定性文件\n\n以下文件尚未列入备份规则，未备份：\n\n"
            summary += "\n".join(f"- {r['id']}/{p}" for r in coverage["roots"] for p in r["unclassified"]["samples"]) + "\n"
        if not coverage["totals"]["complete"]:
            summary += "\n部分文件夹因链接、读取限制或排除设置未完成检查，请核对覆盖报告。\n"
    writer.add_report("summary.md", summary)
    if history is not None:
        writer.add_report('history.json', json.dumps({**history.report(), 'agents': sorted({s.agent for s in history.sources}),
                                                    'packages': history.references(destination)},ensure_ascii=False,sort_keys=True)+'\n')
        writer.add_report('history.md', '# 历史记录\n\n历史文件存放在相邻的独立分包中，请一起携带。恢复仅新增，不保证可继续对话。\n')
    plan = BackupPlan(writer, selected, tuple(roots.values()) + ((desktop,) if desktop else ()), config.core_projects, collections, projects, exclusions, warnings, coverage, history)
    plan.check_privacy()
    if not plan.verify_sources_unchanged():
        raise BundleError("a selected source changed during collection")
    return plan


def apply_backup(plan: BackupPlan) -> dict[str, Any]:
    plan.check_privacy()
    validate_output(plan.writer.destination.parent, roots=plan.roots, projects=plan.core_projects)
    if not plan.verify_sources_unchanged():
        raise BundleError("a selected source changed after preview")
    if plan.history is None:
        manifest = plan.writer.finalize(projects=plan.project_result.projects, exclusions=plan.exclusions, warnings=plan.warnings)
    else:
        destination = plan.writer.destination
        final_paths = [*(destination.parent / r['name'] for r in plan.history.references(destination)), destination]
        from .preflight import no_links
        for path in final_paths:
            no_links(path)
            if path.exists():
                raise BundleError('a backup destination already exists')
        staging = destination.parent / ('.ai-machine-stage-' + uuid.uuid4().hex)
        staging.mkdir()
        staged_paths = [staging / destination.name, *(staging / r['name'] for r in plan.history.references(destination))]
        def verify() -> None:
            if not plan.verify_sources_unchanged():
                raise BundleError('a selected source changed while publishing')
        try:
            plan.writer.destination = staged_paths[0]
            manifest = plan.writer.finalize(projects=plan.project_result.projects, exclusions=plan.exclusions, warnings=plan.warnings)
            write_history(plan.history, staged_paths[1:], parent_content_id=manifest['content_id'])
            verify()
            # Main last: an interrupted publication cannot advertise a set
            # until all its history parts have been created.
            publish_files([*staged_paths[1:], staged_paths[0]], final_paths, verify=verify)
        finally:
            plan.writer.destination = destination
            for path in staged_paths:
                path.unlink(missing_ok=True)
            staging.rmdir()
    validate_bundle(plan.writer.destination)
    digest = hashlib.sha256()
    with plan.writer.destination.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if not plan.verify_sources_unchanged():
        raise BundleError("a selected source changed while publishing; retain the zip for review")
    return {**plan.preview(), "mode": "applied", "sha256": digest.hexdigest(),
            "bytes": plan.writer.destination.stat().st_size, "content_id": manifest["content_id"]}
