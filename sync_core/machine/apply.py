"""Recoverable restore plans; all writes go through the existing transaction."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable
import tomlkit

from sync_core.transaction import PlannedChanges, transaction, write_file
from sync_core.utils import digest

from .bundle import BundleError
from .preflight import Preflight, get_field, no_links, safe_destination, target_bytes
from .paths import norm
from .procs import running_apps


def _put(raw: Any, key: str, value: Any) -> None:
    parts=key.split('.')
    target=raw
    for part in parts[:-1]:
        if part not in target:
            target[part]={}
        if not hasattr(target[part],'keys'):
            raise BundleError('target setting section is not a table')
        target=target[part]
    target[parts[-1]]=value


@dataclass
class RestorePlan:
    check: Preflight
    changes: PlannedChanges
    boundaries: dict[Path,Path]
    conflicts: list[dict[str,Any]]
    skipped: list[dict[str,Any]]
    restored: list[dict[str,Any]]
    warnings: list[str]
    process_names: tuple[str,...]
    required_projects: tuple[Path,...]

    def report(self) -> dict[str,Any]:
        return {'mode':'preview','writes':len(self.changes),'conflicts':self.conflicts,'skipped':self.skipped,
                'restored':self.restored,'warnings':self.warnings,'running':self.check.running}


def plan_restore(check: Preflight, *, state: Path, process_names: tuple[str,...],
                 overwrite: Iterable[Path] = (), prefer_bundle: Iterable[str] = (),
                 confirm_security: bool = False, security_hash: str | None = None,
                 include_memory: bool = True, workbuddy_files: bool = False,
                 codex_trust: bool = False, confirm_trust: str | None = None) -> RestorePlan:
    if security_hash is not None and (not confirm_security or security_hash!=check.security_list_hash):
        raise BundleError('security confirmation no longer matches displayed list')
    if codex_trust and confirm_trust!=check.trust_list_hash:
        raise BundleError('trust confirmation no longer matches displayed list')
    no_links(state)
    changes=PlannedChanges(state_root=state,metadata={'operation':'machine_restore','path_agents':{},
                                                      'path_boundaries':{},
                                                      'content_id':check.manifest['content_id']})
    if codex_trust:
        changes.metadata['trust_list_hash']=confirm_trust
    if confirm_security:
        changes.metadata['security_list_hash']=security_hash or check.security_list_hash
    boundaries={};conflicts=[];skipped=[];restored=[];warnings=[];required_projects=set()
    overwrites={Path(path).absolute() for path in overwrite}
    preferred=set(prefer_bundle)

    def add(path: Path, data: bytes, item, *, expected: bytes | None, merge: bool=False) -> None:
        boundary=item.boundary
        if boundary is None or not path.is_relative_to(boundary):
            raise BundleError('write escaped restoration boundary')
        no_links(path)
        if path in changes and changes[path]!=data and not merge:
            raise BundleError('multiple entries propose different destination bytes')
        changes[path]=data
        changes.expected[path]=digest(expected)
        changes.metadata['path_agents'][str(path)]=item.entry['agent']
        changes.metadata['path_boundaries'][str(path)]=str(boundary)
        boundaries[path]=boundary

    for item in check.items:
        entry=item.entry
        record={'entry_id':entry['id'],'agent':entry['agent'],'kind':entry['kind'],
                'target':str(item.target) if item.target else None}
        if item.reason or item.target is None:
            skipped.append({**record,'reason':item.reason})
            continue
        target=item.target
        changes.expected[target]=digest(item.current)
        if entry['agent'].startswith('workbuddy') and not workbuddy_files:
            skipped.append({**record,'reason':'manual_workbuddy'})
            continue
        if entry['agent'].startswith('workbuddy') and '打开 WorkBuddy，确认人设与记忆可见；文本写回不代表自动加载成功。' not in warnings:
            warnings.append('打开 WorkBuddy，确认人设与记忆可见；文本写回不代表自动加载成功。')
        if entry['kind']=='memory' and entry['agent']=='claude' and not include_memory:
            skipped.append({**record,'reason':'memory_not_selected'})
            continue
        if entry['kind']=='memory' and entry['agent']=='claude':
            candidates=[record for record in check.manifest['projects'] if record['git_root_id']==entry['project_id']]
            required_projects.update(check.projects[record['project_id']] for record in candidates if check.projects[record['project_id']] is not None)
        if entry['kind']=='trust_fields':
            if not codex_trust or item.fields['trust_level']!='trusted':
                skipped.append({**record,'reason':'trust_not_confirmed'})
                continue
            project=check.projects[entry['project_id']]
            if project is None or not project.is_dir():
                raise BundleError('confirmed trust folder disappeared')
            no_links(project)
            required_projects.add(project)
            if item.status=='differs':
                conflicts.append({**record,'reason':'trust_differs','path':item.fields['path']})
                continue
            if item.status=='new':
                prior=changes.get(target,item.current)
                raw=tomlkit.parse(prior.decode('utf-8')) if prior else tomlkit.document()
                if 'projects' not in raw:
                    raw['projects']=tomlkit.table()
                path=item.fields['path']
                existing=next((key for key in raw['projects'] if norm(key,check.target_os).casefold()==path.casefold()),path) if check.target_os in {'windows','nt','win32'} else path
                if existing not in raw['projects']:
                    raw['projects'][existing]=tomlkit.table()
                raw['projects'][existing]['trust_level']='trusted'
                add(target,tomlkit.dumps(raw).encode('utf-8'),item,expected=item.current,merge=True)
            restored.append({**record,'trust_path':item.fields['path'],'trust_level':'trusted'})
            continue
        if entry['kind']=='settings_fields':
            prior=changes.get(target,item.current)
            raw=(json.loads(prior) if entry['agent']=='claude' else tomlkit.parse(prior.decode('utf-8'))) if prior else ({} if entry['agent']=='claude' else tomlkit.document())
            changed=False
            applied_fields={}
            for key,value in item.fields.items():
                status=item.field_status[key]
                if key in item.confirm and not confirm_security:
                    skipped.append({**record,'field':key,'reason':'security_not_confirmed'})
                    continue
                if status=='differs' and key not in preferred:
                    conflicts.append({**record,'field':key,'reason':'field_differs'})
                    continue
                if status!='same':
                    _put(raw,key,value)
                    changed=True
                applied_fields[key]=value
            if changed:
                data=((json.dumps(raw,ensure_ascii=False,indent=2)+'\n').encode('utf-8') if entry['agent']=='claude'
                      else tomlkit.dumps(raw).encode('utf-8'))
                add(target,data,item,expected=item.current,merge=True)
            if applied_fields:
                restored.append({**record,'fields':applied_fields})
            continue
        if entry['kind']=='permissions_local':
            try:
                relative=target.relative_to(item.boundary).as_posix()
                probe=subprocess.run(['git','ls-files','--error-unmatch','--',relative],cwd=item.boundary,
                                     capture_output=True,timeout=5)
                if probe.returncode==0:
                    warnings.append('一个已批准操作文件被 Git 跟踪，请在助手中核对其来源。')
            except (OSError,subprocess.TimeoutExpired):
                pass
        if item.status=='same':
            restored.append({**record,'sha256':entry['sha256']})
            continue
        destination=target
        current=item.current
        if item.status=='differs' and target.absolute() not in overwrites:
            destination=safe_destination(item.boundary,target.relative_to(item.boundary).as_posix()+'.from-bundle')
            alternate=target_bytes(destination)
            conflicts.append({**record,'saved_as':str(destination),'reason':'file_differs'})
            if entry['kind']=='memory' and target.name=='MEMORY.md':
                warnings.append('记忆索引已有不同内容；现有版本保留，请对照另存版本手动整理。')
            if alternate is not None and alternate!=item.data:
                skipped.append({**record,'reason':'alternate_already_differs'})
                continue
            if alternate==item.data:
                changes.expected[destination]=digest(alternate)
                restored.append({**record,'target':str(destination),'sha256':entry['sha256']})
                continue
            current=alternate
        add(destination,item.data,item,expected=current)
        restored.append({**record,'target':str(destination),'sha256':entry['sha256']})
    return RestorePlan(check,changes,boundaries,conflicts,skipped,restored,warnings,process_names,tuple(required_projects))


def apply_restore(plan: RestorePlan, *, processes: Iterable[str] | None = None,
                  writer: Callable[[Path,bytes|None],None] | None = None) -> dict[str,Any]:
    running=running_apps(plan.process_names,processes=processes)
    if running:
        raise BundleError('target application is running')
    for key,current in (('trust_list_hash',plan.check.trust_list_hash),('security_list_hash',plan.check.security_list_hash)):
        if key in plan.changes.metadata and plan.changes.metadata[key]!=current:
            raise BundleError('confirmed list changed')
    for project in plan.required_projects:
        no_links(project)
        if not project.is_dir():
            raise BundleError('required project disappeared')
    for path in plan.changes.expected:
        no_links(path)
        if digest(target_bytes(path))!=plan.changes.expected[path]:
            raise BundleError('target changed since check')
    if not plan.changes:
        return {**plan.report(),'mode':'applied','backup':None}
    write=writer or write_file
    def guarded(path: Path,data: bytes|None) -> None:
        no_links(path)
        boundary=plan.boundaries[path]
        if not boundary.is_dir() or not path.resolve().is_relative_to(boundary.resolve()):
            raise BundleError('destination boundary changed')
        if running_apps(plan.process_names,processes=processes):
            raise BundleError('target application started during restore')
        write(path,data)
        if digest(target_bytes(path))!=digest(data):
            raise BundleError('write verification failed')
    state=plan.changes.state_root
    no_links(state)
    backup=transaction(plan.changes,state/'backups',state_root=state,writer=guarded)
    return {**plan.report(),'mode':'applied','backup':str(backup) if backup else None}
