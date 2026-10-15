import os
from pathlib import Path
import subprocess

import pytest

from sync_core.machine.skills_links import link_target
from sync_core.machine.bundle import BundleError
from sync_core.machine.backup import prepare_backup,apply_backup
from sync_core.machine.config import load_config
from sync_core.machine.preflight import preflight


def link(path,target):
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        path.symlink_to(target,target_is_directory=True)
    except OSError:
        if os.name!='nt':raise
        q=lambda v:"'"+str(v).replace("'","''")+"'"
        result=subprocess.run(['powershell','-NoProfile','-Command','New-Item -ItemType Junction -Path '+q(path)+' -Target '+q(target)+' | Out-Null'],capture_output=True,timeout=15)
        if result.returncode:pytest.skip('Windows cannot create fixture symlink or junction')


def test_allowed_link_source_and_restore_native_destination(tmp_path):
    home=tmp_path/'home';root=home/'.claude';root.mkdir(parents=True)
    approved=home/'.cc-switch/skills';(approved/'own').mkdir(parents=True)
    (approved/'own/SKILL.md').write_text('approved body')
    link(root/'skills',approved)
    assert link_target(home,root)==(approved.resolve(),True)
    out=tmp_path/'out';out.mkdir()
    plan=prepare_backup(home=home,config=load_config(tmp_path/'none.json',home=home),out=out,environ={},agents=frozenset({'claude'}),software={'versions':{}},git_keys=[])
    assert any(e['archive_path']=='files/claude/main/skills/own/SKILL.md' for e in plan.writer.entries)
    covered = next(r for r in plan.coverage['roots'] if r['id'] == 'claude_home')
    assert covered['by_nature']['A']['carried'] == 1 and covered['complete']
    assert not covered['pruned']
    assert any(r.skills[0]['via']=='approved-link' for r in plan.collections if getattr(r,'skills',None))
    apply_backup(plan)
    target=tmp_path/'target';(target/'.claude').mkdir(parents=True)
    native=preflight(plan.writer.destination,home=target,config=load_config(tmp_path/'none2.json',home=target),environ={},processes=[])
    skill=next(i for i in native.items if i.entry['kind']=='skills')
    assert skill.target==target/'.claude/skills/own/SKILL.md'
    foreign=target/'.cc-switch/skills';foreign.mkdir(parents=True)
    link(target/'.claude/skills',foreign)
    blocked=preflight(plan.writer.destination,home=target,config=load_config(tmp_path/'none2.json',home=target),environ={},processes=[])
    assert next(i for i in blocked.items if i.entry['kind']=='skills').reason=='link_blocked'


@pytest.mark.parametrize('case',['outside','target_link','inner_link'])
def test_reject_unsafe_approved_links(tmp_path,case):
    home=tmp_path/'home';root=home/'.claude';root.mkdir(parents=True)
    approved=home/'.cc-switch/skills';outside=tmp_path/'outside';outside.mkdir()
    if case=='target_link':link(approved,outside)
    else:approved.mkdir(parents=True)
    if case=='inner_link':link(approved/'inner',outside)
    link(root/'skills',outside if case=='outside' else approved)
    with pytest.raises(BundleError,match='E7501'):
        link_target(home,root)
