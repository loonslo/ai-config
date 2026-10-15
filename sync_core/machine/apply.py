"""Recoverable restore plans; all writes go through the existing transaction."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
import tomlkit

from sync_core.transaction import PlannedChanges, transaction, write_file
from sync_core.utils import digest
from sync_core.streaming import StreamContent, content_digest, file_digest

from .bundle import BundleError
from .preflight import Preflight, get_field, no_links, safe_destination, target_bytes, fields_parent
from .paths import norm, derive_project_dir, git_root
from .procs import running_apps
from .exports import account_skill_zip, environment_script
from .history import HistoryError


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
    export_changes: dict[Path, bytes] = field(default_factory=dict, repr=False)
    export_expected: dict[Path, str | None] = field(default_factory=dict, repr=False)

    def report(self) -> dict[str,Any]:
        return {'mode':'preview','writes':len(self.changes),'conflicts':self.conflicts,'skipped':self.skipped,
                'pending_conflicts':sum(item.get('decision')=='pending' for item in self.conflicts),
                'restored':self.restored,'warnings':self.warnings,'running':self.check.running,
                'exports': [{'target': str(path), 'name': path.name} for path in self.export_changes]}


def plan_restore(check: Preflight, *, state: Path, process_names: tuple[str,...],
                 overwrite: Iterable[Path] = (), prefer_bundle: Iterable[str] = (),
                 confirm_security: bool = False, security_hash: str | None = None,
                 include_memory: bool = True, workbuddy_files: bool = False,
                 codex_trust: bool = False, confirm_trust: str | None = None,
                 conflict_choices: Mapping[str,str] | None = None) -> RestorePlan:
    if security_hash is not None and (not confirm_security or security_hash!=check.security_list_hash):
        raise BundleError('security confirmation no longer matches displayed list')
    if codex_trust and confirm_trust!=check.trust_list_hash:
        raise BundleError('trust confirmation no longer matches displayed list')
    if conflict_choices is not None and (
        set(conflict_choices)-{item.entry['id'] for item in check.items}
        or any(value not in {'overwrite','keep'} for value in conflict_choices.values())
    ):
        raise BundleError('invalid conflict choice')
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
    export_items: dict[Path, list] = {}
    export_changes: dict[Path, bytes] = {}
    export_expected: dict[Path, str | None] = {}
    field_proposals: dict[tuple[Path,tuple[str,...],str],Any] = {}
    if check.history is not None:
        if not check.history.verify_unchanged():
            raise HistoryError()
        redacted_history={r['logical_path'] for r in json.loads(check.files.get('reports/flagged.json',b'{"items":[]}'))['items'] if r.get('action')=='redacted'}
        for source in check.history.sources:
            agent=source['agent'];relative=source['relative'];sid=source['source_id']
            record={'entry_id':'history:'+sid,'agent':agent,'kind':'history_files',
                    'logical_path':f'{agent}:history/{relative}','sha256':source['sha256'],'streamed':True,
                    'redacted':f'{agent}:history/{relative}' in redacted_history}
            if agent not in check.agents:
                skipped.append({**record,'reason':'agent_not_selected'});continue
            boundary=check.roots[agent];mapped_project=None;unmapped=False
            if agent=='claude' and relative.startswith('projects/'):
                encoded=relative.split('/')[1];matches=set()
                for project in check.manifest['projects']:
                    target_project=check.projects.get(project['project_id'])
                    if target_project is None:
                        continue
                    for key in ('source_path','git_root'):
                        name=derive_project_dir(project.get(key,''))
                        equals=name is not None and (name.casefold()==encoded.casefold() if check.manifest['source']['os'] in {'windows','nt','win32'} else name==encoded)
                        if equals:
                            matches.add(target_project if key=='source_path' else git_root(target_project))
                if len(matches)==1:
                    mapped_project=matches.pop()
                    name=derive_project_dir(mapped_project)
                    if name is not None:
                        relative=f'projects/{name}/{relative.split("/")[-1]}'
                    else:
                        unmapped=True
                else:
                    unmapped=True
                if unmapped:
                    boundary=check.report_dir
                    relative=f'history-unmapped/claude/{sid[:16]}/{relative.split("/")[-1]}'
                    mapped_project=None
            if not unmapped and not boundary.is_dir():
                skipped.append({**record,'reason':'agent_not_initialized'});continue
            try:
                target=safe_destination(boundary,relative)
                original=target
                for index in range(1000):
                    if not target.exists() and target not in changes:
                        break
                    p=Path(relative)
                    alternate=(p.parent/f'{p.stem}.from-history-{sid[:12]}-{index+1}{p.suffix}').as_posix()
                    target=safe_destination(boundary,alternate)
                else:
                    raise BundleError('too many existing history copies')
            except (OSError,BundleError):
                skipped.append({**record,'reason':'unsafe_target'});continue
            changes[target]=check.history.content(source)
            changes.expected[target]=None
            changes.metadata['path_agents'][str(target)]=agent
            changes.metadata['path_boundaries'][str(target)]=str(boundary)
            changes.metadata.setdefault('stream_paths',[]).append(str(target))
            boundaries[target]=boundary
            if mapped_project is not None:
                required_projects.add(mapped_project)
            restored.append({**record,'target':str(target),'history_unmapped':unmapped,'saved_as':str(target) if target!=original else None})
        warnings.append('历史仅新增或另存，不保证可继续对话；未映射的项目转录请在报告文件夹核对。')

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
                'logical_path':entry['logical_path'],
                'conflict_group':entry.get('conflict_group'),
                'conflict_scope': ':'.join(str(entry.get(k) or '') for k in ('agent','instance','project_id','holder')),
                'project':str(check.projects.get(entry.get('project_id')) or ''),
                'target':str(item.target) if item.target else None}
        choice=conflict_choices.get(entry['id'],'pending') if conflict_choices is not None else None
        if item.reason or item.target is None:
            skipped.append({**record,'reason':item.reason})
            continue
        target=item.target
        if entry.get('restore') == 'export':
            export_items.setdefault(target, []).append(item)
            continue
        if entry['agent'] == 'shared' and target.name == '.skill-lock.json' and item.current is not None:
            skipped.append({**record, 'reason': 'kept_local'})
            continue
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
            candidates=[record for record in check.manifest['projects'] if record.get('git_root_id',record['project_id'])==entry['project_id']]
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
            if item.status=='differs' or (choice is not None and item.current is not None and item.status=='new'):
                conflicts.append({**record,'reason':'trust_differs' if item.status=='differs' else 'trust_missing','path':item.fields['path'],
                                  **({'decision':choice} if choice else {})})
                if choice!='overwrite':
                    if choice=='keep':
                        skipped.append({**record,'reason':'kept_local'})
                    continue
            if item.status in {'new','differs'}:
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
            editable=[key for key in item.fields if item.field_status[key]!='same'
                      and (key not in item.confirm or confirm_security)]
            if choice is not None and item.current is not None and editable:
                conflicts.extend({**record,'field':key,'reason':'field_differs' if item.field_status[key]=='differs' else 'field_missing',
                                  'decision':choice} for key in editable)
                if choice!='overwrite':
                    if choice=='keep':
                        skipped.append({**record,'reason':'kept_local'})
                    continue
            prior=changes.get(target,item.current)
            raw=(json.loads(prior) if target.suffix == '.json' else tomlkit.parse(prior.decode('utf-8'))) if prior else ({} if target.suffix == '.json' else tomlkit.document())
            parent=fields_parent(raw,item.field_path,create=True) if item.field_path else raw
            changed=False
            applied_fields={}
            for key,value in item.fields.items():
                status=item.field_status[key]
                if key in item.confirm and not confirm_security:
                    skipped.append({**record,'field':key,'reason':'security_not_confirmed'})
                    continue
                if status=='differs' and choice is None and key not in preferred:
                    conflicts.append({**record,'field':key,'reason':'field_differs'})
                    continue
                scope=item.field_path
                if scope and scope[0]=='projects' and check.target_os in {'windows','nt','win32'}:
                    scope=(scope[0],norm(scope[1],check.target_os).casefold(),*scope[2:])
                identity=(target,scope,key)
                if identity in field_proposals and field_proposals[identity]!=value:
                    raise BundleError('多个来源设置落在同一位置且内容不同，请选择不同的工作文件夹，或保留其中一份。')
                field_proposals[identity]=value
                if status!='same':
                    _put(parent,key,value)
                    changed=True
                applied_fields[key]=value
            if changed:
                data=((json.dumps(raw,ensure_ascii=False,indent=2)+'\n').encode('utf-8') if target.suffix == '.json'
                      else tomlkit.dumps(raw).encode('utf-8'))
                add(target,data,item,expected=item.current,merge=True)
            if applied_fields:
                restored.append({**record,'fields':applied_fields})
            continue
        if item.status=='same':
            restored.append({**record,'sha256':entry['sha256']})
            continue
        if item.status=='differs' and choice is not None:
            conflicts.append({**record,'reason':'file_differs','decision':choice})
            if choice!='overwrite':
                if choice=='keep':
                    skipped.append({**record,'reason':'kept_local'})
                continue
        destination=target
        current=item.current
        if item.status=='differs' and choice is None and target.absolute() not in overwrites:
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
    for target, items in export_items.items():
        if items[0].entry['kind'] == 'skills':
            data = account_skill_zip(items)
            artifacts = {target: data}
        else:
            script, names = environment_script(items[0].data)
            artifacts = {target: script, target.with_name('env-vars.md'): names}
        for path, data in artifacts.items():
            current = target_bytes(path)
            if current is not None and current != data:
                raise BundleError('export report already exists with different contents')
            export_changes[path] = data
            export_expected[path] = digest(current)
        for item in items:
            entry = item.entry
            restored.append({'entry_id': entry['id'], 'agent': entry['agent'], 'kind': entry['kind'],
                             'logical_path': entry['logical_path'], 'target': str(target),
                             'sha256': digest(artifacts[target]), 'exported': True})
    return RestorePlan(check,changes,boundaries,conflicts,skipped,restored,warnings,process_names,tuple(required_projects),
                       export_changes, export_expected)


def apply_restore(plan: RestorePlan, *, processes: Iterable[str] | None = None,
                  writer: Callable[[Path,bytes|None],None] | None = None) -> dict[str,Any]:
    if any(item.get('decision')=='pending' for item in plan.conflicts):
        raise BundleError('choose overwrite or keep before restoring')
    running=running_apps(plan.process_names,processes=processes)
    if running:
        raise BundleError('target application is running')
    if plan.check.history is not None and not plan.check.history.verify_unchanged():
        raise HistoryError()
    for key,current in (('trust_list_hash',plan.check.trust_list_hash),('security_list_hash',plan.check.security_list_hash)):
        if key in plan.changes.metadata and plan.changes.metadata[key]!=current:
            raise BundleError('confirmed list changed')
    for project in plan.required_projects:
        no_links(project)
        if not project.is_dir():
            raise BundleError('required project disappeared')
    for path in plan.changes.expected:
        no_links(path)
        expected_hash=file_digest(path) if str(path) in plan.changes.metadata.get('stream_paths',[]) else digest(target_bytes(path))
        if expected_hash!=plan.changes.expected[path]:
            raise BundleError('target changed since check')
    for path, expected in plan.export_expected.items():
        no_links(path)
        if digest(target_bytes(path)) != expected:
            raise BundleError('export target changed since check')
        if plan.check.report_dir is None or not path.is_relative_to(plan.check.report_dir):
            raise BundleError('export escaped report directory')
    # Exports are deliberate report artifacts, excluded from restore/undo
    # transactions. Atomic exclusive creation prevents overwriting reports.
    for path, data in plan.export_changes.items():
        if plan.export_expected[path] is not None:
            continue
        no_links(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + '.partial')
        created = False
        try:
            with partial.open('xb') as handle:
                created = True
                handle.write(data)
                handle.flush()
            no_links(path)
            if path.exists():
                raise BundleError('export target appeared during write')
            partial.rename(path)
        finally:
            if created:
                partial.unlink(missing_ok=True)
    if not plan.changes:
        return {**plan.report(),'mode':'applied','backup':None}
    write=writer or write_file
    def guarded(path: Path,data: bytes|None|StreamContent) -> None:
        no_links(path)
        boundary=plan.boundaries[path]
        if not boundary.exists() and boundary in {plan.check.roots.get('shared'),plan.check.report_dir}:
            no_links(boundary)
            boundary.mkdir(parents=True, exist_ok=False)
        if not boundary.is_dir() or not path.resolve().is_relative_to(boundary.resolve()):
            raise BundleError('destination boundary changed')
        if running_apps(plan.process_names,processes=processes):
            raise BundleError('target application started during restore')
        write(path,data)
        actual=file_digest(path) if str(path) in plan.changes.metadata.get('stream_paths',[]) else digest(target_bytes(path))
        if actual!=content_digest(data):
            raise BundleError('write verification failed')
    state=plan.changes.state_root
    no_links(state)
    backup=transaction(plan.changes,state/'backups',state_root=state,writer=guarded)
    return {**plan.report(),'mode':'applied','backup':str(backup) if backup else None}
