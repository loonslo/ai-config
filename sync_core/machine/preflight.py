"""Read-only destination resolution and per-file/field comparisons."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import re
from typing import Any, Iterable, Mapping
import tomllib

from sync_core.utils import digest
from .privacy import private_text, private_metadata

from .backup import AGENTS, agent_roots
from .bundle import BundleError, PrivateContentError, UnsupportedBundle, MAX_FILE_BYTES, read_bundle
from .catalog import CLAUDE_FIELDS_AUTO, CLAUDE_FIELDS_CONFIRM, CODEX_DESKTOP_FIELDS, CODEX_FIELDS_CONFIRM, allowed_item, denied_path, classify
from ..layout import data_root
from .settings import CLAUDE_CONFIRM_EXTRA, safe_environment, mcp_field
from .privacy import secret_name, secret_hits
from .source_roots import desktop_root
from .config import MachineConfig
from .guided import AGENT_LABELS, KIND_LABELS
from .paths import RootMap, derive_project_dir, git_root, norm, real_case
from .procs import running_apps
from .coverage import safe_name
from .groups import entry_group, selected_groups, group_counts, DEFAULT_GROUPS
from .history_restore import HistorySet, history_report, load_history
from .history import history_path


class UnsafeTarget(BundleError):
    pass


def no_links(path: Path) -> None:
    for parent in (path, *path.parents):
        if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
            raise UnsafeTarget("linked destination")


def safe_destination(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if (not root.is_absolute() or not relative or relative.startswith('/') or '\\' in relative
            or any(part in {'.', '..', ''} or ':' in part or part.endswith(('.', ' '))
                   or re.search(r'[<>"|?*\x00-\x1f]', part)
                   or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',part) for part in parts)
            or denied_path(relative)):
        raise BundleError("unsafe restore destination")
    path = root.joinpath(*parts)
    no_links(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise BundleError("destination escaped root")
    return path


def target_bytes(path: Path) -> bytes | None:
    no_links(path)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise UnsafeTarget("target cannot be compared safely")
    with path.open('rb') as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise UnsafeTarget("target exceeds size limit")
    return data


def list_hash(items: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _flatten(value: Mapping[str, Any], prefix: str = '') -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, item in value.items():
        key = f'{prefix}.{name}' if prefix else name
        if not isinstance(name, str) or '.' in name:
            raise BundleError('invalid field name')
        if isinstance(item, dict):
            result.update(_flatten(item, key))
        else:
            result[key] = item
    return result


def get_field(raw: Mapping[str,Any], key: str) -> tuple[bool,Any]:
    value: Any=raw
    for part in key.split('.'):
        if not isinstance(value,Mapping) or part not in value:
            return False,None
        value=value[part]
    return True,value


def fields_parent(raw: dict, path: tuple[str,...], *, create: bool = False) -> dict:
    """Project keys are whole path segments and may contain dots or slashes."""
    for name in path:
        if name not in raw:
            if not create:
                return {}
            raw[name] = {}
        raw = raw[name]
        if not isinstance(raw,dict):
            raise BundleError('invalid settings parent')
    return raw


def allowed_fields(agent: str, data: bytes, *, target_os: str, source_name: str = '') -> tuple[dict[str, Any], set[str]]:
    raw = json.loads(data)
    if not isinstance(raw, dict) or not isinstance(raw.get('fields'), dict):
        raise BundleError('invalid settings payload')
    fields = _flatten(raw['fields'])
    confirm = set(CLAUDE_FIELDS_CONFIRM if agent == 'claude' else CODEX_FIELDS_CONFIRM)
    for key in fields:
        if source_name in {'.mcp.json', 'claude_desktop_config.json', '.claude.json'}:
            allowed = mcp_field(key) or (source_name=='claude_desktop_config.json' and key.startswith('preferences.')) or (
                source_name=='.claude.json' and key in {'enabledMcpjsonServers','disabledMcpjsonServers','allowedTools'})
            confirm.add(key)
        elif agent == 'claude':
            allowed = key in {*CLAUDE_FIELDS_AUTO, *CLAUDE_FIELDS_CONFIRM} or key.startswith('env.') or key.startswith(tuple(k + '.' for k in CLAUDE_CONFIRM_EXTRA)) or key in CLAUDE_CONFIRM_EXTRA
            if key.startswith('env.') or key.split('.')[0] in CLAUDE_CONFIRM_EXTRA:
                confirm.add(key)
            if key.startswith('mcpServers.'):
                allowed = mcp_field(key)
        else:
            allowed = (key in {'model_reasoning_effort', 'personality', 'history.persistence', 'windows.sandbox', *CODEX_FIELDS_CONFIRM}
                       or key.startswith(('features.', 'memories.'))
                       or key in {f'desktop.{name}' for name in CODEX_DESKTOP_FIELDS})
            if key.startswith('shell_environment_policy.set.') or key.startswith('mcp_servers.') and key.endswith('.url'):
                allowed = True
                confirm.add(key)
        if '.env.' in key or key.startswith(('env.', 'shell_environment_policy.set.')):
            if secret_name(key.rsplit('.', 1)[-1]) or secret_hits(json.dumps(fields[key], ensure_ascii=False)):
                raise BundleError('credential in environment setting')
        if not allowed:
            raise BundleError('field outside approved catalog')
    if target_os not in {'windows', 'nt', 'win32'}:
        fields.pop('windows.sandbox', None)
    return fields, confirm


@dataclass
class CheckItem:
    entry: dict[str, Any]
    target: Path | None
    boundary: Path | None
    data: bytes
    current: bytes | None
    status: str
    reason: str = ''
    fields: dict[str, Any] | None = None
    field_status: dict[str, str] | None = None
    confirm: set[str] | None = None
    field_path: tuple[str,...] = ()

    def report(self) -> dict[str, Any]:
        return {'entry_id': self.entry['id'], 'agent': self.entry.get('agent'), 'kind': self.entry.get('kind'),
                'target': str(self.target) if self.target else None, 'status': self.status,
                'reason': self.reason, 'fields': self.field_status or {}}


@dataclass
class Preflight:
    manifest: dict[str, Any]
    files: dict[str, bytes]
    items: list[CheckItem]
    roots: dict[str, Path]
    projects: dict[str, Path | None]
    agents: frozenset[str]
    running: list[str]
    trust_list: list[dict[str, Any]]
    security_list: list[dict[str, Any]]
    software_warnings: list[str]
    target_os: str
    report_dir: Path | None = None
    groups: frozenset[str] = DEFAULT_GROUPS
    history: HistorySet | None = None

    @property
    def trust_list_hash(self) -> str:
        return list_hash(self.trust_list)

    @property
    def security_list_hash(self) -> str:
        return list_hash(self.security_list)

    def report(self) -> dict[str, Any]:
        counts=group_counts([i.entry for i in self.items if i.reason!='group_not_selected'])
        if self.history is not None:
            selected=[s for s in self.history.sources if s['agent'] in self.agents]
            counts['history']={'files':len(selected),'bytes':sum(s['size'] for s in selected)}
        history_logical={f"{s['agent']}:history/{s['relative']}" for s in self.history.sources if s['agent'] in self.agents} if self.history else set()
        redacted_history=sum(r.get('action')=='redacted' and r.get('logical_path') in history_logical
                             for r in json.loads(self.files.get('reports/flagged.json',b'{"items":[]}'))['items'])
        return {'counts': dict(Counter(item.status for item in self.items)), 'running': self.running,
                'projects': {pid: str(path) if path else None for pid, path in self.projects.items()},
                'items': [item.report() for item in self.items], 'trust_list': self.trust_list,
                'trust_list_hash': self.trust_list_hash, 'security_list': self.security_list,
                'security_list_hash': self.security_list_hash, 'software_warnings': self.software_warnings,
                'bundle_groups': sorted({entry_group(e) for e in self.manifest['entries'] if entry_group(e)} | ({'history'} if 'reports/history.json' in self.files else set())),
                'history': self.history.report if self.history else None,
                'by_group': counts,
                'redacted_todo': redacted_history + sum(any(f.startswith('redacted:') for f in i.entry['flags']) for i in self.items if i.reason!='group_not_selected'),
                'needs_rebuild': len({i.entry.get('provenance_id',i.entry['id']) for i in self.items if i.reason!='group_not_selected' and any(f.startswith('artifacts_excluded:') for f in i.entry['flags'])}),
                'exports': list({str(i.target):{'kind':i.entry['kind'],'name':i.target.name,'target':str(i.target)}
                                 for i in self.items if i.target and i.entry.get('restore')=='export'}.values())}

    def markdown(self) -> str:
        counts = Counter(item.status for item in self.items)
        lines = ['# 恢复前检查', '', f"可新增 {counts['new']} 项；相同 {counts['same']} 项；内容不同 {counts['differs']} 项；暂不能处理 {counts['blocked']} 项。",
                 f"找不到的工作文件夹 {sum(path is None for path in self.projects.values())} 个。", '']
        if self.running:
            lines += ['请先关闭这些正在运行的程序：' + '、'.join(self.running), '']
        labels = {'new':'可以新增','same':'已相同','differs':'保留现有，另存备份版本','blocked':'暂不能处理'}
        reasons = {'agent_not_initialized':'请先安装并启动助手一次','project_missing':'工作文件夹不存在',
                   'manual_trust':'Claude 信任暂由你手动确认','manual_workbuddy':'WorkBuddy 文本需明确选择手动还原',
                   'unsafe_target':'文件无法安全读取或路径含链接','link_blocked':'目标文件夹被链接接管，已跳过'}
        for item in self.items:
            line = f"- {AGENT_LABELS[item.entry['agent']]} {KIND_LABELS[item.entry['kind']]}：{labels[item.status]}"
            if item.reason:
                line += '；' + reasons.get(item.reason, '需要人工核对')
            lines.append(line + '。')
            if item.target:
                lines.append(f'  {safe_name(str(item.target))}')
        lines += ['', '## 需要你确认', '', f'涉及安全或模型选择的设置 {len(self.security_list)} 项；Codex 文件夹信任 {len(self.trust_list)} 项，默认不恢复。', '']
        lines.extend('- ' + warning for warning in self.software_warnings)
        return '\n'.join(lines) + '\n'

    def todo(self) -> str:
        flagged = json.loads(self.files.get('reports/flagged.json', b'{"items":[]}'))
        selected_logical={i.entry['logical_path'] for i in self.items if i.reason!='group_not_selected'}
        selected_skills={i.entry.get('provenance_id') for i in self.items if i.reason!='group_not_selected'}
        if self.history:
            selected_logical.update(f"{s['agent']}:history/{s['relative']}" for s in self.history.sources if s['agent'] in self.agents)
        redacted = ''.join(f"- {safe_name(item['logical_path'])}：第 {', '.join(map(str, item['lines']))} 行密钥已隐藏，请重新填写。\n"
                           for item in flagged.get('items', []) if item.get('action') == 'redacted' and item.get('logical_path') in selected_logical)
        exported = ''.join(f"- {safe_name(str(item.target))}：已导出到恢复报告文件夹，请自行导入；若登录后已自动出现，可跳过。\n"
                           for item in self.items if item.entry.get('restore') == 'export' and item.target)
        skills = json.loads(self.files.get('reports/skills.json', b'{"skills":[]}'))
        rebuild = ''.join('- '+safe_name(item['name'])+'：有程序文件未携带，请按来源说明重新安装或构建。\n'
                          for item in skills.get('skills',[]) if any(e.get('reason')!='git_metadata_excluded' for e in item.get('excluded',[])) and item.get('id') in selected_skills)
        return ('# 接下来要做的事\n\n- 按登录清单重新登录、填写密钥和授权服务。\n'
                '- 按重装清单安装第三方技能、插件和服务连接工具。\n'
                '- 打开 WorkBuddy，确认人设与记忆可见；文本写回不代表自动加载成功。\n'
                '- 在 Claude 与 Codex 中手动添加工作文件夹，确认信任选择。\n'
                '- 在新会话里按核验说明确认规则和记忆已生效。\n' +
                ('- 历史只新增或另存，不保证可继续对话；未映射转录请核对 history-unmapped 文件夹。\n' if self.history else '') + redacted + exported + rebuild)


def _content_gate(manifest: dict, files: dict[str, bytes], *, config: MachineConfig, roots: dict,
                  projects: dict, records: dict, mapper: RootMap, system: str, report_dir: Path) -> None:
    try:
        raw = json.loads(files.get('reports/skills.json', b'{"skills":[]}'))
        values = raw.get('skills') if isinstance(raw,dict) else None
        if not isinstance(values,list) or any(not isinstance(r,dict) or not isinstance(r.get('id'),str) or not isinstance(r.get('name'),str) for r in values):
            raise ValueError()
        provenance = {r['id']:r for r in values}
        if len(provenance)!=len(values):raise ValueError()
        flagged = json.loads(files.get('reports/flagged.json', b'{"items":[]}'))
        items = flagged.get('items') if isinstance(flagged,dict) else None
        if not isinstance(items,list):raise ValueError()
        logical = {e['logical_path'] for e in manifest['entries']} | {e['logical_path'] for e in manifest['exclusions'] if isinstance(e,dict) and 'logical_path' in e}
        history=history_report(files)
        if history:
            for item in items:
                name=item.get('logical_path','') if isinstance(item,dict) else ''
                for agent in ('claude','codex'):
                    prefix=agent+':history/'
                    if name.startswith(prefix) and history_path(agent,name[len(prefix):]):
                        logical.add(name)
        for item in items:
            if (not isinstance(item,dict) or item.get('logical_path') not in logical or
                not isinstance(item.get('lines'),list) or any(type(n) is not int or n<1 for n in item['lines']) or
                item.get('action') not in {'redacted','skipped','kept_heuristic','kept_override'}):
                raise ValueError()
    except (ValueError,TypeError,KeyError):
        raise BundleError('invalid privacy or skills report') from None
    for index, entry in enumerate(manifest['entries'], 1):
        hits = secret_hits(files[entry['archive_path']])
        if not hits:continue
        flags=entry['flags']
        if 'secret_override' in flags:
            target, _, reason = _destination(entry,roots=roots,projects=projects,records=records,mapper=mapper,system=system,report_dir=report_dir)
            if not reason and target in config.allow_secret_hit_paths:
                continue
        evidence=provenance.get(entry.get('provenance_id'),{})
        source=evidence.get('source',{})
        if (entry['kind']=='skills' and entry.get('rule_id')=='SK-02' and entry.get('group')=='skills_third' and
            evidence.get('origin')=='third_party' and isinstance(source,dict) and source.get('confidence') in {'exact','derived'} and
            source.get('evidence') in {'skill-lock','git-remote+HEAD','package.json','tmpl-sibling'} and
            all(hit.confidence=='heuristic' for hit in hits) and ('kept_heuristic' in flags or entry.get('redactions',0)>0)):
            continue
        raise PrivateContentError(report=entry['kind']=='report', index=index, hits=hits)


def _destination(entry: dict[str, Any], *, roots: dict[str, Path], projects: dict[str, Path | None],
                 records: dict[str, dict[str, Any]], mapper: RootMap, system: str,
                 report_dir: Path | None = None) -> tuple[Path | None, Path | None, str]:
    agent, kind, archive = entry.get('agent'), entry.get('kind'), entry['archive_path']
    if agent not in AGENTS | {'system'} or kind not in KIND_LABELS:
        raise UnsupportedBundle()
    if entry.get('restore') == 'export':
        if report_dir is None:
            raise BundleError('export requires a report directory')
        no_links(report_dir)
        if agent == 'system' and kind == 'env_fields' and archive == 'files/system/main/env.fields.json':
            return safe_destination(report_dir, 'restore-env.ps1'), report_dir, ''
        if agent == 'claude' and entry.get('instance') == 'desktop' and kind == 'skills':
            from .exports import account_member
            account, name, _ = account_member(archive)
            folder = f'account-skills/{account}/' if account else 'account-skills/'
            return safe_destination(report_dir, folder + name + '.zip'), report_dir, ''
        raise BundleError('unsupported export destination')
    if agent == 'claude' and kind == 'settings_fields' and archive == 'files/claude/main/claude-json.fields.json':
        home = roots['shared'].parent
        return safe_destination(home, '.claude.json'), home, ''
    if agent == 'claude' and entry.get('instance') == 'desktop' and kind == 'settings_fields':
        desktop = roots.get('claude_desktop')
        if desktop is None or not desktop.is_dir():
            return None, None, 'agent_not_initialized'
        if archive != 'files/claude/desktop/desktop-config.fields.json':
            raise BundleError('invalid desktop setting entry')
        return safe_destination(desktop, 'claude_desktop_config.json'), desktop, ''
    root = roots[agent]
    no_links(root)
    if not root.is_dir() and agent != 'shared':
        return None, None, 'agent_not_initialized'
    prefix = f'files/{agent}/{agent if agent.startswith("workbuddy") else "main"}/'
    if archive.startswith('files/projects/'):
        pieces = archive.split('/',4)
        if len(pieces)==5 and agent=='claude' and kind=='memory':
            candidates=[record for record in records.values() if record.get('git_root_id',record['project_id'])==pieces[2]]
            if pieces[3]!='claude' or pieces[2]!=entry.get('project_id') or not pieces[4].startswith('memory/') or not candidates:
                raise BundleError('memory outside core projects')
            if not any(projects[record['project_id']] is not None for record in candidates):
                return None,None,'project_missing'
            mapped=mapper.map(candidates[0].get('git_root',candidates[0]['source_path']))
            target_root=Path(mapped) if mapped else None
            if target_root is None or not target_root.is_dir():
                return None,None,'project_missing'
            no_links(target_root)
            encoded=derive_project_dir(str(git_root(target_root)))
            if encoded is None:
                raise BundleError('unsupported memory directory')
            tail=pieces[4][len('memory/'):]
            if not tail.endswith('.md'):
                raise BundleError('unapproved memory file')
            directory=root/'projects'/encoded
            if system in {'windows','nt','win32'}:
                directory=real_case(directory)
            return safe_destination(directory/'memory',tail),root,''
        if len(pieces)!=5 or pieces[3]!=agent or pieces[2]!=entry.get('project_id') or pieces[2] not in records:
            raise BundleError('invalid project entry')
        project, relative = projects[pieces[2]], pieces[4]
        if project is None:
            return None, None, 'project_missing'
        if kind == 'trust_fields':
            if relative != 'trust.fields.json':
                raise BundleError('invalid trust entry')
            if agent == 'claude':
                return None, None, 'manual_trust'
            if agent != 'codex':
                raise BundleError('invalid trust agent')
            return safe_destination(root, 'config.toml'), root, ''
        parts = PurePosixPath(relative).parts
        if kind in {'rules', 'skills', 'customizations', 'approvals', 'scripts', 'settings_fields'}:
            if agent=='claude' and kind=='settings_fields' and relative=='claude-json.fields.json':
                home = roots['shared'].parent
                return safe_destination(home,'.claude.json'),home,''
            decision = classify('project:' + pieces[2], relative, scope='project')
            if kind == 'settings_fields' and relative == 'mcp.fields.json':
                return safe_destination(project, '.mcp.json'), project, ''
            if decision.action in {'carry', 'fields'} and decision.nature not in {'D', 'E', 'F'}:
                return safe_destination(project, relative), project, ''
        if agent == 'claude':
            if kind!='permissions_local' or parts[-2:]!=('.claude','settings.local.json') or len(parts)>4:
                raise BundleError('invalid project permissions')
        elif agent.startswith('workbuddy'):
            index = next((i for i,p in enumerate(parts) if p==f'.{agent}'),-1)
            if index<0 or index>2:
                raise BundleError('invalid project WorkBuddy entry')
            item=allowed_item(agent,agent,'/'.join(parts[index:]),scope='project')
            if item is None or item.kind!=kind:
                raise BundleError('unapproved WorkBuddy project path')
        else:
            raise BundleError('unapproved project destination')
        return safe_destination(project,relative), project, ''
    if not archive.startswith(prefix):
        raise BundleError('invalid agent entry')
    relative=archive[len(prefix):]
    if kind in {'skills', 'approvals', 'customizations', 'scripts', 'plans'} or kind == 'memory' and agent == 'codex':
        source_root = {'claude': 'claude_home', 'codex': 'codex_home', 'shared': 'agents_home', 'workbuddy-ai': 'workbuddy_ai'}.get(agent, agent)
        decision = classify(source_root, relative)
        if decision.action != 'carry' or decision.nature in {'D', 'E', 'F'}:
            raise BundleError('destination outside approved catalog')
        if kind == 'skills' and agent == 'shared' and relative == '.skill-lock.json':
            # Written only if absent; never merged or overwritten.
            path = root / relative
            no_links(path)
            return path, root, ''
        return safe_destination(root, relative), root, ''
    if kind=='settings_fields':
        expected='settings.fields.json' if agent=='claude' else 'config.fields.json'
        if agent not in {'claude','codex'} or relative!=expected:
            raise BundleError('invalid settings destination')
        return safe_destination(root,'settings.json' if agent=='claude' else 'config.toml'),root,''
    if kind=='memory' and agent=='claude':
        raise BundleError('memory requires a core project identity')
    item=allowed_item(agent,agent if agent.startswith('workbuddy') else 'main',relative)
    if item is None or item.kind!=kind or entry.get('mode')!='file':
        raise BundleError('destination outside approved catalog')
    return safe_destination(root,relative),root,''


def preflight(bundle: Path, *, home: Path, config: MachineConfig, agents: frozenset[str] | None = None,
              environ: Mapping[str,str] | None = None, os_name: str | None = None,
              root_map: RootMap | None = None, processes: Iterable[str] | None = None,
              software: dict[str,Any] | None = None, report_dir: Path | None = None,
              groups: frozenset[str] | None = None) -> Preflight:
    import os
    system=os_name or platform.system().lower()
    manifest,files=read_bundle(bundle)
    if private_metadata(manifest):
        raise PrivateContentError(metadata=True)
    roots=agent_roots(home,config,os.environ if environ is None else environ)
    desktop = desktop_root(home, os.environ if environ is None else environ)
    if desktop is not None:
        roots['claude_desktop'] = desktop
    selected=agents if agents is not None else frozenset(AGENTS)
    chosen_groups=selected_groups(groups)
    history=load_history(bundle,manifest,files,selected='history' in chosen_groups)
    if not selected or selected-AGENTS:
        raise BundleError('invalid agent selection')
    source=manifest.get('source',{})
    if not isinstance(source,dict) or not isinstance(source.get('os'),str):
        raise BundleError('invalid source metadata')
    mapper=root_map or RootMap(config.root_map.rules,source['os'],system)
    exports = report_dir or data_root(home=home, environ=dict(environ or {})) / 'state' / 'machine-reports' / manifest['content_id'][:16]
    if not exports.is_absolute():
        raise BundleError('invalid report directory')
    no_links(exports)
    records: dict[str,dict[str,Any]]={}
    projects: dict[str,Path|None]={}
    if not isinstance(manifest['projects'],list):
        raise BundleError('invalid projects')
    for record in manifest['projects']:
        if not isinstance(record,dict) or any(not isinstance(record.get(key),str) for key in ('project_id','source_path')) or any(key in record and not isinstance(record[key],str) for key in ('git_root','git_root_id')):
            raise BundleError('invalid project record')
        pid=record['project_id']
        if pid in records:
            raise BundleError('duplicate project identity')
        records[pid]=record
        mapped=mapper.map(record['source_path'])
        path=Path(mapped) if mapped else None
        if path is not None:
            no_links(path)
        projects[pid]=path if path is not None and path.is_absolute() and path.is_dir() else None
    if any(exports.resolve().is_relative_to(root.resolve()) for root in (*roots.values(), *[p for p in projects.values() if p])):
        raise BundleError('report directory may not be inside restoration roots')
    _content_gate(manifest,files,config=config,roots=roots,projects=projects,records=records,mapper=mapper,system=system,report_dir=exports)
    items=[]; trusts=[]; security=[]
    for entry in manifest['entries']:
        if entry.get('kind')=='report' and entry.get('agent')=='report':
            continue
        if entry.get('agent') not in selected and entry.get('agent') != 'system':
            if entry.get('agent') not in AGENTS:
                raise BundleError('invalid agent')
            continue
        data=files[entry['archive_path']]
        if entry_group(entry) not in chosen_groups:
            items.append(CheckItem(entry,None,None,data,None,'blocked','group_not_selected'))
            continue
        try:
            target,boundary,reason=_destination(entry,roots=roots,projects=projects,records=records,mapper=mapper,system=system,report_dir=exports)
            current=target_bytes(target) if target else None
        except UnsafeTarget as error:
            target,boundary,reason,current=None,None,'link_blocked' if entry['kind']=='skills' and str(error)=='linked destination' else 'unsafe_target',None
        except OSError:
            target,boundary,reason,current=None,None,'unsafe_target',None
        fields=None; states=None; confirm=None; field_path=()
        status='blocked' if reason else 'new' if current is None else 'same' if current==data else 'differs'
        if not reason and entry['kind']=='settings_fields':
            fields,confirm=allowed_fields(entry['agent'],data,target_os=system,source_name=target.name)
            raw={} if current is None else json.loads(current) if target.suffix == '.json' else tomllib.loads(current.decode('utf-8'))
            if not isinstance(raw,dict):
                raise BundleError('invalid target settings')
            if target.name=='.claude.json' and entry.get('project_id'):
                if any(not mcp_field(key) for key in fields):
                    raise BundleError('field outside project service catalog')
                project = norm(projects[entry['project_id']],system)
                table = fields_parent(raw,('projects',))
                existing = next((key for key in table if isinstance(key,str) and (
                    norm(key,system).casefold()==project.casefold() if system in {'windows','nt','win32'} else norm(key,system)==project)),project)
                field_path=('projects',existing)
                raw=fields_parent(raw,field_path)
            states={key:'new' if not get_field(raw,key)[0] else 'same' if get_field(raw,key)[1]==value else 'differs' for key,value in fields.items()}
            status='differs' if 'differs' in states.values() else 'new' if 'new' in states.values() else 'same'
            security.extend({'entry_id':entry['id'],'agent':entry['agent'],'instance':entry['instance'],
                             'project':str(projects[entry['project_id']]) if entry.get('project_id') else None,
                             'field':key,'value':fields[key],'target':str(target)}
                            for key in sorted(fields) if key in confirm and states[key]!='same')
        if not reason and entry['kind']=='trust_fields' and entry['agent']=='codex':
            raw=json.loads(data)
            if raw.get('trust_level') not in {'trusted','untrusted'}:
                raise BundleError('invalid trust level')
            path=projects[entry['project_id']]
            level=raw['trust_level']
            destination=norm(path,system).lower() if system in {'windows','nt','win32'} else norm(path,system)
            existing=tomllib.loads(current.decode('utf-8')) if current else {}
            tables=existing.get('projects',{})
            found=next((table for key,table in tables.items() if norm(key,system).casefold()==destination.casefold()),{}) if system in {'windows','nt','win32'} else tables.get(destination,{})
            value=found.get('trust_level') if isinstance(found,dict) else None
            status='new' if value is None else 'same' if value==level else 'differs'
            fields={'path':destination,'trust_level':level}
            if level=='trusted':
                trusts.append({'entry_id':entry['id'],'path':destination,'trust_level':level,'status':status})
        items.append(CheckItem(entry,target,boundary,data,current,status,reason,fields,states,confirm,field_path))
    configured=config.running_process_names
    observed=running_apps(configured,processes=processes)
    software_warnings=[]
    if software is not None and 'reports/software.json' in files:
        prior=json.loads(files['reports/software.json']).get('versions',{})
        for name,value in prior.items():
            actual=software.get('versions',{}).get(name)
            if value and not actual:
                software_warnings.append(f'需要安装软件：{name}')
            elif value and actual and str(value).lstrip('v').split('.')[0]!=str(actual).lstrip('v').split('.')[0]:
                software_warnings.append(f'软件主要版本不同：{name}')
    return Preflight(manifest,files,items,roots,projects,selected,observed,sorted(trusts,key=lambda x:x['path']),
                     security,software_warnings,system,exports,chosen_groups,history)
