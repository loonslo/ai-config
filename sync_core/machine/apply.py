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

    def report(self) -> dict[str,Any]:
        return {'mode':'preview','writes':len(self.changes),'conflicts':self.conflicts,'skipped':self.skipped,
                'restored':self.restored,'warnings':self.warnings,'running':self.check.running}


def plan_restore(check: Preflight, *, state: Path, process_names: tuple[str,...],
                 overwrite: Iterable[Path] = (), prefer_bundle: Iterable[str] = (),
                 confirm_security: bool = False, security_hash: str | None = None,
                 include_memory: bool = False, workbuddy_files: bool = False,
                 codex_trust: bool = False, confirm_trust: str | None = None) -> RestorePlan:
    if security_hash is not None and (not confirm_security or security_hash!=check.security_list_hash):
        raise BundleError('security confirmation no longer matches displayed list')
    if codex_trust and confirm_trust!=check.trust_list_hash:
        raise BundleError('trust confirmation no longer matches displayed list')
    no_links(state)
    changes=PlannedChanges(state_root=state,metadata={'operation':'machine_restore','path_agents':{},
                                                      'content_id':check.manifest['content_id']})
    boundaries={};conflicts=[];skipped=[];restored=[];warnings=[]
    overwrites={Path(path).absolute() for path in overwrite}
    preferred=set(prefer_bundle)

    def add(path: Path, data: bytes, item, *, expected: bytes | None) -> None:
        boundary=item.boundary
        if boundary is None or not path.is_relative_to(boundary):
            raise BundleError('write escaped restoration boundary')
        no_links(path)
        if path in changes and changes[path]!=data:
            raise BundleError('multiple entries propose different destination bytes')
        changes[path]=data
        changes.expected[path]=digest(expected)
        changes.metadata['path_agents'][str(path)]=item.entry['agent']
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
        if entry['kind']=='memory' and entry['agent']=='claude' and not include_memory:
            skipped.append({**record,'reason':'memory_not_selected'})
            continue
        if entry['kind']=='trust_fields':
            if not codex_trust or item.fields['trust_level']!='trusted':
                skipped.append({**record,'reason':'trust_not_confirmed'})
                continue
            # MK-32 extends this guarded branch; never default to trust.
            skipped.append({**record,'reason':'trust_engine_pending'})
            continue
        if entry['kind']=='settings_fields':
            raw=(json.loads(item.current) if entry['agent']=='claude' else tomlkit.parse(item.current.decode('utf-8'))) if item.current else ({} if entry['agent']=='claude' else tomlkit.document())
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
                add(target,data,item,expected=item.current)
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
    return RestorePlan(check,changes,boundaries,conflicts,skipped,restored,warnings,process_names)


def apply_restore(plan: RestorePlan, *, processes: Iterable[str] | None = None,
                  writer: Callable[[Path,bytes|None],None] | None = None) -> dict[str,Any]:
    running=running_apps(plan.process_names,processes=processes)
    if running:
        raise BundleError('target application is running')
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
