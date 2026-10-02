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

from sync_core.utils import SECRET, digest

from .backup import AGENTS, agent_roots
from .bundle import BundleError, MAX_FILE_BYTES, read_bundle
from .catalog import CLAUDE_FIELDS_AUTO, CLAUDE_FIELDS_CONFIRM, CODEX_DESKTOP_FIELDS, CODEX_FIELDS_CONFIRM, allowed_item, denied_path
from .config import MachineConfig
from .guided import AGENT_LABELS, KIND_LABELS
from .paths import RootMap, derive_project_dir, git_root, norm, real_case
from .procs import running_apps


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


def allowed_fields(agent: str, data: bytes, *, target_os: str) -> tuple[dict[str, Any], set[str]]:
    raw = json.loads(data)
    if not isinstance(raw, dict) or not isinstance(raw.get('fields'), dict):
        raise BundleError('invalid settings payload')
    fields = _flatten(raw['fields'])
    confirm = set(CLAUDE_FIELDS_CONFIRM if agent == 'claude' else CODEX_FIELDS_CONFIRM)
    for key in fields:
        if agent == 'claude':
            allowed = key in {*CLAUDE_FIELDS_AUTO, *CLAUDE_FIELDS_CONFIRM}
        else:
            allowed = (key in {'model_reasoning_effort', 'personality', 'history.persistence', 'windows.sandbox', *CODEX_FIELDS_CONFIRM}
                       or key.startswith(('features.', 'memories.'))
                       or key in {f'desktop.{name}' for name in CODEX_DESKTOP_FIELDS})
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

    @property
    def trust_list_hash(self) -> str:
        return list_hash(self.trust_list)

    @property
    def security_list_hash(self) -> str:
        return list_hash(self.security_list)

    def report(self) -> dict[str, Any]:
        return {'counts': dict(Counter(item.status for item in self.items)), 'running': self.running,
                'projects': {pid: str(path) if path else None for pid, path in self.projects.items()},
                'items': [item.report() for item in self.items], 'trust_list': self.trust_list,
                'trust_list_hash': self.trust_list_hash, 'security_list': self.security_list,
                'security_list_hash': self.security_list_hash, 'software_warnings': self.software_warnings}

    def markdown(self) -> str:
        counts = Counter(item.status for item in self.items)
        lines = ['# 恢复前检查', '', f"可新增 {counts['new']} 项；相同 {counts['same']} 项；内容不同 {counts['differs']} 项；暂不能处理 {counts['blocked']} 项。",
                 f"找不到的工作文件夹 {sum(path is None for path in self.projects.values())} 个。", '']
        if self.running:
            lines += ['请先关闭这些正在运行的程序：' + '、'.join(self.running), '']
        labels = {'new':'可以新增','same':'已相同','differs':'保留现有，另存备份版本','blocked':'暂不能处理'}
        reasons = {'agent_not_initialized':'请先安装并启动助手一次','project_missing':'工作文件夹不存在',
                   'manual_trust':'Claude 信任暂由你手动确认','manual_workbuddy':'WorkBuddy 文本需明确选择手动还原',
                   'unsafe_target':'文件无法安全读取或路径含链接'}
        for item in self.items:
            line = f"- {AGENT_LABELS[item.entry['agent']]} {KIND_LABELS[item.entry['kind']]}：{labels[item.status]}"
            if item.reason:
                line += '；' + reasons.get(item.reason, '需要人工核对')
            lines.append(line + '。')
            if item.target:
                lines.append(f'  {item.target}')
        lines += ['', '## 需要你确认', '', f'涉及安全或模型选择的设置 {len(self.security_list)} 项；Codex 文件夹信任 {len(self.trust_list)} 项，默认不恢复。', '']
        lines.extend('- ' + warning for warning in self.software_warnings)
        return '\n'.join(lines) + '\n'

    def todo(self) -> str:
        return ('# 接下来要做的事\n\n- 按登录清单重新登录、填写密钥和授权服务。\n'
                '- 按重装清单安装第三方技能、插件和服务连接工具。\n'
                '- 打开 WorkBuddy，确认人设与记忆可见；文本写回不代表自动加载成功。\n'
                '- 在 Claude 与 Codex 中手动添加工作文件夹，确认信任选择。\n'
                '- 在新会话里按核验说明确认规则和记忆已生效。\n')


def _destination(entry: dict[str, Any], *, roots: dict[str, Path], projects: dict[str, Path | None],
                 records: dict[str, dict[str, Any]], mapper: RootMap, system: str) -> tuple[Path | None, Path | None, str]:
    agent, kind, archive = entry.get('agent'), entry.get('kind'), entry['archive_path']
    if agent not in AGENTS or kind not in KIND_LABELS:
        raise BundleError('unsupported restoration entry')
    root = roots[agent]
    no_links(root)
    if not root.is_dir():
        return None, None, 'agent_not_initialized'
    prefix = f'files/{agent}/{agent if agent.startswith("workbuddy") else "main"}/'
    if archive.startswith('files/projects/'):
        pieces = archive.split('/',4)
        if len(pieces)==5 and agent=='claude' and kind=='memory':
            candidates=[record for record in records.values() if record.get('git_root_id')==pieces[2]]
            if pieces[3]!='claude' or pieces[2]!=entry.get('project_id') or not pieces[4].startswith('memory/') or not candidates:
                raise BundleError('memory outside core projects')
            mapped=mapper.map(candidates[0]['git_root'])
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
              software: dict[str,Any] | None = None) -> Preflight:
    import os
    system=os_name or platform.system().lower()
    manifest,files=read_bundle(bundle)
    roots=agent_roots(home,config,os.environ if environ is None else environ)
    selected=agents if agents is not None else frozenset(AGENTS)
    if not selected or selected-AGENTS:
        raise BundleError('invalid agent selection')
    source=manifest.get('source',{})
    if not isinstance(source,dict) or not isinstance(source.get('os'),str):
        raise BundleError('invalid source metadata')
    mapper=root_map or RootMap(config.root_map.rules,source['os'],system)
    records: dict[str,dict[str,Any]]={}
    projects: dict[str,Path|None]={}
    if not isinstance(manifest['projects'],list):
        raise BundleError('invalid projects')
    for record in manifest['projects']:
        if not isinstance(record,dict) or any(not isinstance(record.get(key),str) for key in ('project_id','source_path','git_root','git_root_id')):
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
    items=[]; trusts=[]; security=[]
    for entry in manifest['entries']:
        if entry.get('kind')=='report' and entry.get('agent')=='report':
            continue
        if entry.get('agent') not in selected:
            if entry.get('agent') not in AGENTS:
                raise BundleError('invalid agent')
            continue
        data=files[entry['archive_path']]
        if SECRET.search(data.decode('utf-8',errors='replace')):
            raise BundleError('credential-like restored content')
        try:
            target,boundary,reason=_destination(entry,roots=roots,projects=projects,records=records,mapper=mapper,system=system)
            current=target_bytes(target) if target else None
        except (OSError,UnsafeTarget):
            target,boundary,reason,current=None,None,'unsafe_target',None
        fields=None; states=None; confirm=None
        status='blocked' if reason else 'new' if current is None else 'same' if current==data else 'differs'
        if not reason and entry['kind']=='settings_fields':
            fields,confirm=allowed_fields(entry['agent'],data,target_os=system)
            raw={} if current is None else json.loads(current) if entry['agent']=='claude' else tomllib.loads(current.decode('utf-8'))
            if not isinstance(raw,dict):
                raise BundleError('invalid target settings')
            states={key:'new' if not get_field(raw,key)[0] else 'same' if get_field(raw,key)[1]==value else 'differs' for key,value in fields.items()}
            status='differs' if 'differs' in states.values() else 'new' if 'new' in states.values() else 'same'
            security.extend({'entry_id':entry['id'],'agent':entry['agent'],'field':key,'value':fields[key],'target':str(target)}
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
        items.append(CheckItem(entry,target,boundary,data,current,status,reason,fields,states,confirm))
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
                     security,software_warnings,system)
