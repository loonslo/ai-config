"""Machine-only undo using the shared journal selection and transaction APIs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any,Iterable

from sync_core.restore import recent_operations,select_operation,plan_restore
from sync_core.transaction import transaction,write_file

from .bundle import BundleError
from .preflight import no_links,target_bytes
from .procs import running_apps


def operations(state: Path) -> list[dict[str,Any]]:
    no_links(state)
    undone=set()
    directory=state/'transactions'
    if directory.is_dir():
        for path in directory.glob('*.json'):
            no_links(path)
            raw=json.loads(target_bytes(path))
            if raw.get('status')=='COMMITTED' and raw.get('metadata',{}).get('operation')=='machine_undo':
                undone.add(raw['metadata'].get('restored_operation'))
    return [item for item in recent_operations(state,limit=1000,operation_filter='machine_restore') if item['operation_id'] not in undone]


def prepare_undo(state: Path, *, index: int | None=None, operation_id: str | None=None):
    choices=operations(state)
    if operation_id is None:
        if index is None or index<1 or index>len(choices):
            raise BundleError('select an available machine restore')
        operation_id=choices[index-1]['operation_id']
    if not any(item['operation_id']==operation_id for item in choices):
        raise BundleError('operation not available for machine undo')
    selected=select_operation(state,operation_id=operation_id,operation_filter='machine_restore')
    journal=json.loads(target_bytes(Path(selected['journal_path'])))
    metadata=journal.get('metadata',{})
    boundaries={Path(key):Path(value) for key,value in metadata.get('path_boundaries',{}).items()}
    for change in selected['changes']:
        target=Path(change['path'])
        no_links(target)
        if target not in boundaries or not target.is_relative_to(boundaries[target]):
            raise BundleError('undo destination outside recorded boundary')
    backup=Path(selected['backup'])
    no_links(backup)
    if not backup.resolve().is_relative_to((state/'backups').resolve()):
        raise BundleError('undo backup escaped state directory')
    records=json.loads(target_bytes(backup/'manifest.json'))
    allowed={change['path'] for change in selected['changes']}
    for record in records:
        if record.get('path') not in allowed or not str(record.get('file','')).isdigit():
            raise BundleError('invalid undo backup record')
        no_links(backup/str(record['file']))
    plan=plan_restore(state,selected)
    plan.metadata={'operation':'machine_undo','restored_operation':operation_id,
                   'path_agents':metadata.get('path_agents',{}),'path_boundaries':metadata.get('path_boundaries',{})}
    return selected,plan,boundaries


def undo(state: Path, *, index: int | None=None, operation_id: str | None=None, apply: bool=False,
         process_names: tuple[str,...]=(), processes: Iterable[str] | None=None) -> dict[str,Any]:
    selected,plan,boundaries=prepare_undo(state,index=index,operation_id=operation_id)
    report={'mode':'preview','writes':len(plan),'paths':[str(path) for path in plan],
            'operation_id':selected['operation_id']}
    if not apply:
        return report
    if running_apps(process_names,processes=processes):
        raise BundleError('target application is running')
    def guarded(path,data):
        no_links(path)
        if not path.resolve().is_relative_to(boundaries[path].resolve()):
            raise BundleError('undo boundary changed')
        if running_apps(process_names,processes=processes):
            raise BundleError('target application started during undo')
        write_file(path,data)
        if target_bytes(path)!=data:
            raise BundleError('undo verification failed')
    transaction(plan,state/'backups',state_root=state,writer=guarded)
    return {**report,'mode':'applied'}
