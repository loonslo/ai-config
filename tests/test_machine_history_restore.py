import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from _agent_homes import ReadTracker
from sync_core.machine.backup import prepare_backup, apply_backup
from sync_core.machine.config import load_config
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore, apply_restore
from sync_core.machine.history import HistoryError, HistoryLimits
from sync_core.machine.paths import derive_project_dir, RootMap
from sync_core.machine.verify import verify
from sync_core.machine.undo import undo


def _backup(tmp_path, *, claude=False, secret=False, raw_body=None):
    home=tmp_path/'source';root=home/('.claude' if claude else '.codex');root.mkdir(parents=True)
    project=tmp_path/'old-project';project.mkdir()
    subprocess.run(['git','init',str(project)],capture_output=True,check=True)
    relative=f'projects/{derive_project_dir(project)}/chat.jsonl' if claude else 'sessions/2026/chat.jsonl'
    source=root/relative;source.parent.mkdir(parents=True)
    value='sk-'+'a'*30 if secret else 'hello 中文'
    body=(json.dumps({'message':value},ensure_ascii=False)+'\n').encode('utf-8')*8
    if raw_body is not None:
        relative = 'sessions/2026/content.bin'
        source = root/relative
        body = raw_body
    source.write_bytes(body)
    config=tmp_path/'source-config.json';config.write_text(json.dumps({'core_projects':[str(project)]}))
    out=tmp_path/'out';out.mkdir()
    plan=prepare_backup(home=home,config=load_config(config,home=home),out=out,agents=frozenset({'claude' if claude else 'codex'}),
                        environ={},groups=frozenset({'history'}),software={'versions':{}},git_keys=[],
                        history_limits=HistoryLimits(part_bytes=80,chunk_bytes=40))
    apply_backup(plan)
    target=tmp_path/'target';(target/('.claude' if claude else '.codex')).mkdir(parents=True)
    return plan,target,project,relative,body


def _check(plan,target,tmp_path, *, groups=frozenset({'history'}),mapper=None):
    return preflight(plan.writer.destination,home=target,config=load_config(tmp_path/'none.json',home=target),environ={},processes=[],
                     groups=groups,root_map=mapper,report_dir=tmp_path/'reports')


def test_codex_split_history_restore_verify_and_undo(tmp_path):
    plan,home,_,relative,body=_backup(tmp_path)
    check=_check(plan,home,tmp_path)
    assert check.report()['bundle_groups']==['history'] and check.history.sources[0]['size']==len(body)
    restore=plan_restore(check,state=tmp_path/'state',process_names=())
    result=apply_restore(restore,processes=[])
    target=home/'.codex'/relative
    assert target.read_bytes()==body and result['writes']==1
    verification=verify(check,restored=restore.restored,skipped=restore.skipped)
    assert any(c['kind']=='history_files' and c['status']=='PASS' for c in verification.checks if c.get('kind'))
    undo(tmp_path/'state',operation_id=Path(result['backup']).name,apply=True,processes=[])
    assert not target.exists()


def test_codex_binary_history_restore_verify_and_undo(tmp_path):
    body = (b'\xff\x00binary\n' + '中文😀'.encode('utf-16-le')) * 20
    plan, home, _, relative, _ = _backup(tmp_path, raw_body=body)
    check = _check(plan, home, tmp_path)
    restore = plan_restore(check, state=tmp_path/'state', process_names=())
    result = apply_restore(restore, processes=[])
    target = home/'.codex'/relative
    assert target.read_bytes() == body and result['writes'] == 1
    assert any(c.get('kind') == 'history_files' and c['status'] == 'PASS' for c in verify(check, restored=restore.restored).checks)
    undo(tmp_path/'state', operation_id=Path(result['backup']).name, apply=True, processes=[])
    assert not target.exists()


def test_existing_history_is_never_read_or_overwritten(tmp_path,monkeypatch):
    plan,home,_,relative,body=_backup(tmp_path)
    target=home/'.codex'/relative;target.parent.mkdir(parents=True);target.write_bytes(b'original history')
    tracker=ReadTracker(monkeypatch)
    check=_check(plan,home,tmp_path);restore=plan_restore(check,state=tmp_path/'state',process_names=())
    apply_restore(restore,processes=[])
    assert not tracker.touched([target])
    saved=Path(restore.restored[0]['target']);assert saved!=target and saved.read_bytes()==body
    assert target.read_bytes()==b'original history'


def test_unselected_history_never_opens_sibling_archives_even_if_missing(tmp_path,monkeypatch):
    plan,home,_,_,_=_backup(tmp_path)
    paths=[plan.writer.destination.parent/r['name'] for r in plan.history.references(plan.writer.destination)]
    paths[0].unlink()
    tracker=ReadTracker(monkeypatch)
    check=_check(plan,home,tmp_path,groups=frozenset({'rules'}))
    assert check.history is None and check.report()['bundle_groups']==['history']
    restore=plan_restore(check,state=tmp_path/'state',process_names=())
    assert not restore.changes and not tracker.touched(paths)


def test_missing_part_fails_before_any_target_body_reads(tmp_path,monkeypatch):
    plan,home,_,relative,_=_backup(tmp_path)
    target=home/'.codex'/relative;target.parent.mkdir(parents=True);target.write_bytes(b'original')
    path=plan.writer.destination.parent/plan.history.references(plan.writer.destination)[-1]['name'];path.unlink()
    tracker=ReadTracker(monkeypatch)
    with pytest.raises(HistoryError):_check(plan,home,tmp_path)
    assert not tracker.touched([target]) and target.read_bytes()==b'original'


def test_claude_project_mapping_and_unmapped_report_folder(tmp_path):
    plan,home,project,_,body=_backup(tmp_path,claude=True)
    new=tmp_path/'new-project';new.mkdir();subprocess.run(['git','init',str(new)],capture_output=True,check=True)
    mapper=RootMap(((str(project),str(new)),),'windows','windows')
    check=_check(plan,home,tmp_path,mapper=mapper)
    restore=plan_restore(check,state=tmp_path/'state',process_names=());apply_restore(restore,processes=[])
    target=home/f'.claude/projects/{derive_project_dir(new)}/chat.jsonl'
    assert target.read_bytes()==body and not restore.restored[0]['history_unmapped']
    missing_mapper=RootMap(((str(project),str(tmp_path/'missing-project')),),'windows','windows')
    unmapped=_check(plan,home,tmp_path,mapper=missing_mapper)
    restore2=plan_restore(unmapped,state=tmp_path/'state',process_names=());result=apply_restore(restore2,processes=[])
    saved=Path(restore2.restored[0]['target'])
    assert saved.is_relative_to(tmp_path/'reports/history-unmapped') and saved.read_bytes()==body
    assert restore2.restored[0]['history_unmapped']
    undo(tmp_path/'state',operation_id=Path(result['backup']).name,apply=True,processes=[])
    assert not saved.exists() and target.read_bytes()==body


def test_modified_history_parts_or_late_target_prevent_writes(tmp_path):
    plan,home,_,relative,_=_backup(tmp_path)
    check=_check(plan,home,tmp_path);restore=plan_restore(check,state=tmp_path/'state',process_names=())
    target=home/'.codex'/relative;target.parent.mkdir(parents=True);target.write_bytes(b'later')
    with pytest.raises(ValueError):apply_restore(restore,processes=[])
    assert target.read_bytes()==b'later'
    target.unlink()
    part=check.history.paths[0]
    with part.open('ab') as handle:handle.write(b'changed')
    with pytest.raises(ValueError):apply_restore(restore,processes=[])
    assert not target.exists()


def test_redacted_history_main_report_passes_restore_content_gate(tmp_path):
    plan,home,_,relative,_=_backup(tmp_path,secret=True)
    check=_check(plan,home,tmp_path);restore=plan_restore(check,state=tmp_path/'state',process_names=())
    apply_restore(restore,processes=[])
    assert json.loads((home/'.codex'/relative).read_bytes().splitlines()[0])['message']=='<REDACTED>'
    verification=verify(check,restored=restore.restored)
    assert any(c.get('kind')=='history_files' and c['status']=='MANUAL' and c['reason']=='redacted' for c in verification.checks)
    assert 'codex:history/' in check.todo()
    assert 'codex:history/' not in _check(plan,home,tmp_path,groups=frozenset({'rules'})).todo()


def test_desktop_history_restore_preview_apply_verify_undo_and_stale_archive(tmp_path,monkeypatch):
    from sync_core.application.machine_protocol import MachineProtocol
    from test_machine_desktop import preview, apply
    monkeypatch.setattr('sync_core.machine.procs.process_names',lambda: [])
    plan,home,_,relative,body=_backup(tmp_path)
    protocol=MachineProtocol(tmp_path/'device.json',home=home,environ={})
    params={'bundle':str(plan.writer.destination),'agents':['codex'],'groups':['history']}
    old=preview(protocol,'machine_restore',**params)
    assert old['can_apply'], {k:old['result'].get(k) for k in ('running','pending_conflicts','writes','can_apply')}
    assert old['result']['bundle_agents']==['codex'] and old['result']['bundle_groups']==['history']
    part=plan.writer.destination.parent/plan.history.references(plan.writer.destination)[0]['name']
    with part.open('ab') as handle:handle.write(b'zip metadata changed')
    assert apply(protocol,old)['error']['code']=='E_PLAN_STALE'
    assert not (home/'.codex'/relative).exists()
    fresh=preview(protocol,'machine_restore',**params)
    result=apply(protocol,fresh)
    assert result['status']=='applied',result
    assert (home/'.codex'/relative).read_bytes()==body
    assert any(c.get('kind')=='history_files' and c['status']=='PASS' for c in result['result']['verification']['checks'])
    operations=preview(protocol,'machine_history')['result']['operations']
    back=preview(protocol,'machine_undo',operation_id=operations[0]['operation_id'])
    assert apply(protocol,back)['status']=='applied'
    assert not (home/'.codex'/relative).exists()


def test_desktop_missing_history_part_reports_e7507(tmp_path):
    from sync_core.application.machine_protocol import MachineProtocol
    from test_machine_desktop import preview
    plan,home,_,_,_=_backup(tmp_path)
    (plan.writer.destination.parent/plan.history.references(plan.writer.destination)[0]['name']).unlink()
    protocol=MachineProtocol(tmp_path/'device.json',home=home,environ={})
    result=preview(protocol,'machine_restore',bundle=str(plan.writer.destination),agents=['codex'],groups=['history'])
    assert result['error']['code']=='E7507'


def test_history_restore_does_not_cross_target_junction(tmp_path,monkeypatch):
    plan,home,_,_,_=_backup(tmp_path)
    outside=tmp_path/'outside';outside.mkdir();decoy=outside/'chat.jsonl';decoy.write_bytes(b'keep outside')
    junction=home/'.codex/sessions'
    subprocess.run(['cmd','/c','mklink','/J',str(junction),str(outside)],check=True,capture_output=True)
    tracker=ReadTracker(monkeypatch)
    check=_check(plan,home,tmp_path);restore=plan_restore(check,state=tmp_path/'state',process_names=())
    assert not restore.changes and restore.skipped[0]['reason']=='unsafe_target'
    assert not tracker.touched([decoy])
    junction.rmdir()
    assert decoy.read_bytes()==b'keep outside'


@pytest.mark.parametrize('name',['../other.zip','folder/other.zip','C:other.zip','unrelated.zip'])
def test_history_references_cannot_escape_main_folder(name):
    from sync_core.machine.history_restore import history_report
    report={'set_id':'0'*64,'parts':1,'files':1,'bytes':1,'redactions':0,'exclusions':[],'agents':['codex'],
            'packages':[{'name':name,'content_id':'0'*64}]}
    with pytest.raises(HistoryError):history_report({'reports/history.json':json.dumps(report).encode()})
