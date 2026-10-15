import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from sync_core.machine.backup import prepare_backup, apply_backup
from sync_core.machine.bundle import BundleWriter
from sync_core.machine.config import load_config
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore, apply_restore
from sync_core.machine.groups import entry_group, GROUP_LABELS
from sync_core.application.machine_protocol import MachineProtocol, PARAMS
from _agent_homes import ReadTracker


def test_backup_groups_filter_before_body_reads_and_restore_skips_target_reads(tmp_path, monkeypatch):
    home=tmp_path/'source';root=home/'.codex';(root/'memories').mkdir(parents=True)
    (root/'skills/own').mkdir(parents=True)
    (root/'skills/own/SKILL.md').write_text('skill')
    (root/'AGENTS.md').write_text('safe rule')
    (root/'memories/note.md').write_bytes(b'memory')
    tracker=ReadTracker(monkeypatch)
    out=tmp_path/'out';out.mkdir()
    plan=prepare_backup(home=home,config=load_config(tmp_path/'none.json',home=home),out=out,environ={},agents=frozenset({'codex'}),
                        groups=frozenset({'memory'}),software={'versions':{}},git_keys=[])
    assert tracker.touched([root/'AGENTS.md',root/'skills/own/SKILL.md'])==[]
    assert plan.preview()['by_group']=={'memory':{'files':1,'bytes':6}}
    assert not plan.preview()['flagged']['count']
    assert {entry_group(e) for e in plan.writer.entries if e['kind']!='report'}=={'memory'}
    apply_backup(plan)
    target=tmp_path/'target';(target/'.codex').mkdir(parents=True)
    from sync_core.machine import preflight as module
    original=module.target_bytes
    def guard(path):
        assert path != target/'.codex/memories/note.md'
        return original(path)
    monkeypatch.setattr(module,'target_bytes',guard)
    check=preflight(plan.writer.destination,home=target,config=load_config(tmp_path/'none2.json',home=target),environ={},processes=[],groups=frozenset({'rules'}))
    assert check.report()['bundle_groups']==['memory'] and not check.report()['by_group']
    restore=plan_restore(check,state=tmp_path/'state',process_names=())
    assert not restore.changes and restore.skipped[0]['reason']=='group_not_selected'
    monkeypatch.setattr(module,'target_bytes',original)
    check=preflight(plan.writer.destination,home=target,config=load_config(tmp_path/'none2.json',home=target),environ={},processes=[],groups=frozenset({'memory'}))
    apply_restore(plan_restore(check,state=tmp_path/'state',process_names=()),processes=[])
    assert (target/'.codex/memories/note.md').read_bytes()==b'memory'


def test_v1_group_inference_and_location_scoped_skill_conflicts(tmp_path):
    home=tmp_path/'home';(home/'.codex/skills/one').mkdir(parents=True);(home/'.claude/skills/one').mkdir(parents=True)
    old=BundleWriter(tmp_path/'v1.zip',source={'os':'windows'},schema_version=1)
    old.add_file('files/codex/main/AGENTS.md',b'rule',agent='codex',instance='main',kind='rules',logical_path='codex:main/AGENTS.md')
    old.finalize()
    config=load_config(tmp_path/'none.json',home=home)
    check=preflight(old.destination,home=home,config=config,environ={},processes=[],groups=frozenset({'memory'}))
    assert check.report()['bundle_groups']==['rules'] and check.items[0].reason=='group_not_selected'
    writer=BundleWriter(tmp_path/'skills.zip',source={'os':'windows'})
    for agent in ('claude','codex'):
        for name in ('SKILL.md','data.txt'):
            (home/f'.{agent}/skills/one'/name).write_bytes(b'local')
            writer.add_file(f'files/{agent}/main/skills/one/{name}',b'backup',agent=agent,instance='main',kind='skills',logical_path=f'{agent}:main/skills/one/{name}',conflict_group='skill:one',holder=agent+'-global')
    writer.finalize()
    check=preflight(writer.destination,home=home,config=config,environ={},processes=[])
    plan=plan_restore(check,state=tmp_path/'state',process_names=(),conflict_choices={})
    conflicts=plan.report()['conflicts']
    assert len(conflicts)==4 and {c['conflict_group'] for c in conflicts}=={'skill:one'}
    assert len({c['conflict_scope'] for c in conflicts})==2


@pytest.mark.parametrize('extra',[{'groups':['rules','rules']},{'groups':['invalid']},{'groups':[]},{'flagged_policy':'raw'},{'agents':['codex','codex']}])
def test_protocol_rejects_bad_new_params(tmp_path,extra):
    request={'protocol_version':1,'request_id':'test','type':'preview','operation':'machine_backup','params':{'destination':str(tmp_path),**extra}}
    from sync_core.application.protocol import ProtocolError
    with pytest.raises(ProtocolError):MachineProtocol.validate_request(request)
    schema=json.loads(Path('schemas/machine-desktop-rpc.schema.json').read_text())
    assert list(Draft202012Validator(schema).iter_errors(request))


def test_protocol_and_schema_group_enum_match_and_shared_is_supported(tmp_path,monkeypatch):
    schema=json.loads(Path('schemas/machine-desktop-rpc.schema.json').read_text())
    assert set(schema['$defs']['contentGroups']['items']['enum'])==set(GROUP_LABELS)
    assert {'groups','flagged_policy'}<=PARAMS['machine_backup'] and 'groups' in PARAMS['machine_restore']
    req={'protocol_version':1,'request_id':'test','type':'preview','operation':'machine_backup','params':{'destination':str(tmp_path),'agents':['shared'],'groups':['skills_own'],'flagged_policy':'skip'}}
    Draft202012Validator(schema).validate(req);MachineProtocol.validate_request(req)
    home=tmp_path/'home';(home/'.agents').mkdir(parents=True)
    protocol=MachineProtocol(tmp_path/'device.json',home=home,environ={})
    result=protocol.handle({'protocol_version':1,'request_id':'detect','type':'preview','operation':'machine_detect','params':{}})['result']
    assert next(g for g in result['groups'] if g['id']=='history')['default'] is False
    assert next(a for a in result['agents'] if a['id']=='shared')['installed'] is True


def test_project_customizations_follow_own_group_and_unknown_hash_not_diverged(tmp_path):
    from dataclasses import replace
    from sync_core.machine.collect_skills import skills_report
    home=tmp_path/'home';(home/'.codex').mkdir(parents=True)
    project=tmp_path/'project';(project/'.claude/commands').mkdir(parents=True)
    (project/'.claude/commands/one.md').write_text('project command')
    out=tmp_path/'out';out.mkdir()
    config=replace(load_config(tmp_path/'none.json',home=home),core_projects=(project,))
    plan=prepare_backup(home=home,config=config,out=out,environ={},agents=frozenset({'claude','codex'}),
                        groups=frozenset({'skills_own'}),software={'versions':{}},git_keys=[])
    assert any(e['logical_path'].endswith('.claude/commands/one.md') for e in plan.writer.entries)
    data=skills_report([{'name':'same','origin':'vendor_builtin','skill_md_sha256':None}, {'name':'same','origin':'user','skill_md_sha256':'a'*64}])
    assert data['copies'][0]['relation']=='unverified' and data['summary']['diverged_copies']==0
