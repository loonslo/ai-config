"""Additional classified rules/scripts/settings within selected project boundaries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Mapping

from .bundle import BundleError, BundleWriter
from .catalog import classify
from .collect_tier1 import CollectionResult, _files_below, _flags, _read, project_id
from .collect_projects import _owner, _key
from .config import MachineConfig, excluded_path
from .coverage import no_links, observe_fields
from .settings import clean_mcp_servers, field_names
from .source_roots import desktop_root


def tracked_files(project: Path) -> set[str] | None:
    """Legacy helper: no Git inspection; carry every allowlisted assistant file."""
    return set()


def read_source(source: Path, boundary: Path, result: CollectionResult) -> bytes | None:
    try:
        if not no_links(source):
            raise BundleError('linked source')
        data = _read(source, boundary)
        result.source_fingerprints[source] = (hashlib.sha256(data).hexdigest(), source.stat().st_mtime_ns, boundary)
        return data
    except (OSError, ValueError):
        result.warnings.append({'code':'E7101', 'message':'一个已选文件无法安全读取，已跳过。'})
        return None


def add_whole(writer: BundleWriter, result: CollectionResult, source: Path, boundary: Path, *,
              agent: str, relative: str, kind: str, rule_id: str, group: str,
              pid: str | None = None, flags: list[str] | None = None, binary: bool = False) -> None:
    logical = f'project:{pid}/{relative}' if pid else f'{agent}:main/{relative}'
    if not writer.wants(kind,group):
        return
    data = read_source(source, boundary, result)
    if data is None:
        return
    content_flags = _flags(data, rules=kind == 'rules')
    if 'nontext' in content_flags and not binary:
        result.exclusions.append({'logical_path':logical, 'reason':'non_text'})
        return
    data, privacy_flags = writer.prepare_content(data, logical_path=logical, rule_id=rule_id, format_hint=source.suffix.casefold())
    if data is None:
        result.exclusions.append({'logical_path':logical, 'reason':'secret_hit' if writer.flagged_policy == 'skip' else 'skipped_by_policy'})
        return
    archive = f'files/projects/{pid}/{agent}/{relative}' if pid else f'files/{agent}/{agent if agent.startswith("workbuddy") else "main"}/{relative}'
    writer.add_file(archive, data, agent=agent, instance=agent if agent.startswith('workbuddy') else 'main', kind=kind,
                    logical_path=logical, project_id=pid, restore='manual' if agent.startswith('workbuddy') else 'auto',
                    flags=content_flags + privacy_flags + (flags or []), rule_id=rule_id,
                    nature='A', group=group, conflict_group='skill:' + relative.split('/skills/',1)[-1].split('/')[0] if kind == 'skills' else None,
                    redactions=sum(int(f.split(':')[1]) for f in privacy_flags if f.startswith('redacted:')))


def add_fields(writer: BundleWriter, result: CollectionResult, *, source: Path, boundary: Path,
               picked: dict, agent: str, instance: str, filename: str, rule_id: str,
               pid: str | None = None) -> None:
    if not writer.wants('settings_fields'):
        return
    names = field_names(picked)
    if not names:
        return
    logical = f'project:{pid}/{source.name}' if pid else f'{agent}:{instance}/{source.name}'
    data = (json.dumps({'source': logical, 'fields': picked}, ensure_ascii=False, sort_keys=True) + '\n').encode()
    data, flags = writer.prepare_content(data, logical_path=logical, rule_id=rule_id, format_hint='.json')
    if data is None:
        result.exclusions.append({'logical_path':logical, 'reason':'secret_hit' if writer.flagged_policy == 'skip' else 'skipped_by_policy'})
        return
    archive = f'files/projects/{pid}/{agent}/{filename}' if pid else f'files/{agent}/{instance}/{filename}'
    writer.add_file(archive, data, agent=agent, instance=instance, kind='settings_fields', mode='fields', restore='confirm',
                    logical_path=logical, fields=names, confirm_fields=names, flags=flags, rule_id=rule_id,
                    nature='B', group='settings', project_id=pid,
                    redactions=sum(int(f.split(':')[1]) for f in flags if f.startswith('redacted:')))


def collect_classified(writer: BundleWriter, *, home: Path, config: MachineConfig, environ: Mapping[str,str],
                       agents: frozenset[str], roots: dict[str,Path], os_name: str, collect_skills: bool = True) -> CollectionResult:
    result = CollectionResult()
    def excluded(path: Path, boundary: Path) -> bool:
        return excluded_path(path, config=config, home=home, os_name=os_name, boundary=boundary)
    branches = {'claude': ('commands','agents','output-styles','plans','keybindings.json'),
                'codex': ('rules','prompts','memories'), 'workbuddy': ('scripts',), 'workbuddy-ai': ('scripts',)}
    kinds = {'CC-02': ('customizations','skills_own'), 'CC-04': ('plans','memory'),
             'CX-02': ('approvals','approvals'), 'CX-03': ('memory','memory'), 'WB-03': ('scripts','skills_own')}
    for agent, names in branches.items():
        if agent not in agents:
            continue
        root = roots[agent]
        if not root.is_dir() or not no_links(root) or excluded(root, root):
            continue
        for name in names:
            branch = root/name
            sources = [branch] if branch.is_file() and not excluded(branch, root) else _files_below(branch, excluded=lambda p: excluded(p,root))
            for source in sources:
                relative = source.relative_to(root).as_posix()
                decision = classify({'claude':'claude_home','codex':'codex_home','workbuddy-ai':'workbuddy_ai'}.get(agent,agent), relative)
                if decision.rule_id not in kinds:
                    continue
                kind, group = kinds[decision.rule_id]
                add_whole(writer,result,source,root,agent=agent,relative=relative,kind=kind,rule_id=decision.rule_id,group=group)
    for project in config.core_projects:
        if not project.is_dir() or not no_links(project) or excluded(project,project):
            continue
        pid = project_id(project,os_name)
        flags = []
        sources = [project/name for name in ('AGENTS.md','AGENTS.override.md','CLAUDE.md','CLAUDE.local.md','.mcp.json')]
        for branch in ('.claude','.codex','.agents'):
            sources.extend(_files_below(project/branch,excluded=lambda p: excluded(p,project)))
        for source in sources:
            if not source.is_file() or not no_links(source) or excluded(source,project):
                continue
            if _owner(str(source),config.core_projects,os_name) != _key(project,os_name):
                continue
            relative = source.relative_to(project).as_posix()
            decision = classify('project:'+pid,relative,scope='project')
            if decision.action not in {'carry','fields'} or decision.rule_id == 'PJ-02':
                continue
            agent = 'codex' if relative.startswith(('.codex/','.agents/')) or source.name.startswith('AGENTS') else 'claude'
            if agent not in agents:
                continue
            if relative == '.mcp.json':
                data = read_source(source,project,result)
                try:
                    raw = json.loads(data) if data is not None else {}
                    observe_fields(raw,root='project:'+pid,source='.mcp.json',ledger=result.field_ledger)
                    picked = {'mcpServers': clean_mcp_servers(raw.get('mcpServers'))}
                    add_fields(writer,result,source=source,boundary=project,picked=picked,agent=agent,instance='main',filename='mcp.fields.json',rule_id='PJ-05',pid=pid)
                except (ValueError, TypeError):
                    result.warnings.append({'code':'E7102','message':'一个项目服务设置无法解析，已跳过。'})
                continue
            skill = '/skills/' in relative
            if skill and not collect_skills:
                continue
            kind = 'skills' if skill else 'rules' if decision.rule_id == 'PJ-01' or relative.endswith('.md') else 'customizations'
            add_whole(writer,result,source,project,agent=agent,relative=relative,kind=kind,rule_id=decision.rule_id or 'SK-01',
                      group='rules' if decision.rule_id=='PJ-01' else 'skills_own',pid=pid,flags=flags,binary=skill)
    if 'claude' in agents:
        source = home/'.claude.json'
        if source.is_file() and not excluded(source,home):
            data = read_source(source,home,result)
            try:
                raw = json.loads(data) if data is not None else {}
                picked = {key: raw[key] for key in ('enabledMcpjsonServers','disabledMcpjsonServers','allowedTools') if key in raw}
                servers = clean_mcp_servers(raw.get('mcpServers'))
                if servers:
                    picked['mcpServers'] = servers
                add_fields(writer,result,source=source,boundary=home,picked=picked,agent='claude',instance='main',filename='claude-json.fields.json',rule_id='CC-14')
                registered = raw.get('projects', {})
                if isinstance(registered, dict):
                    for project in config.core_projects:
                        if not project.is_dir() or not no_links(project) or excluded(project,project):
                            continue
                        selected = next((value for path,value in registered.items() if isinstance(path,str)
                                         and _key(path,os_name)==_key(project,os_name) and isinstance(value,dict)), {})
                        servers = clean_mcp_servers(selected.get('mcpServers'))
                        if servers:
                            add_fields(writer,result,source=source,boundary=home,picked={'mcpServers':servers},agent='claude',
                                       instance='main',filename='claude-json.fields.json',rule_id='CC-14',pid=project_id(project,os_name))
            except (ValueError,TypeError):
                result.warnings.append({'code':'E7102','message':'助手登记文件的服务设置无法解析，已跳过。'})
        desktop = desktop_root(home,environ)
        if desktop is not None:
            source = desktop/'claude_desktop_config.json'
            if source.is_file() and not excluded(source,desktop):
                data = read_source(source,desktop,result)
                try:
                    raw = json.loads(data) if data is not None else {}
                    picked = {'mcpServers': clean_mcp_servers(raw.get('mcpServers'))}
                    preferences = raw.get('preferences', {})
                    if isinstance(preferences,dict):
                        picked['preferences'] = {k:v for k,v in preferences.items() if isinstance(k,str) and not re.search('device|path|directory|id|token',k,re.I) and not isinstance(v,dict)}
                    observe_fields(raw,root='claude_desktop',source=source.name,ledger=result.field_ledger)
                    add_fields(writer,result,source=source,boundary=desktop,picked=picked,agent='claude',instance='desktop',filename='desktop-config.fields.json',rule_id='CD-03')
                except (ValueError,TypeError):
                    result.warnings.append({'code':'E7102','message':'桌面助手服务设置无法解析，已跳过。'})
    return result
