from dataclasses import replace
import json
from pathlib import Path
import subprocess

import pytest

from sync_core.machine.provenance import ProvenanceHints, resolve_skill
from sync_core.machine.backup import prepare_backup, apply_backup
from sync_core.machine.config import load_config
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore, apply_restore
from sync_core.machine.collect_skills import collect_skills
from sync_core.machine.bundle import BundleWriter, BundleError


def git_skill(path):
    path.mkdir(parents=True,exist_ok=True)
    (path/'SKILL.md').write_text('skill')
    for args in [('init','-q'),('config','user.name','Fixture'),('config','user.email','fixture@example.org'),
                 ('config','remote.origin.url','https://person:pass@example.org/owner/repo.git?private=1'),
                 ('add','SKILL.md'),('commit','-qm','fixture')]:
        subprocess.run(['git','-C',str(path),*args],check=True,capture_output=True)
    return path


def test_non_git_provenance_precedence_and_git_information_ignored(tmp_path, monkeypatch):
    skill = git_skill(tmp_path/'skill')
    def forbidden(*args, **kwargs):
        raise AssertionError('Git must not be queried')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    result = resolve_skill(skill,hints=ProvenanceHints(account={'skill':'user'},vendor_system=True,lock={'skill':{}}))
    assert result['origin']=='user' and result['source']['evidence']=='manifest.creatorType'
    assert resolve_skill(skill,hints=ProvenanceHints(vendor_system=True,lock={'skill':{}}))['origin']=='vendor_builtin'
    locked = resolve_skill(skill,hints=ProvenanceHints(lock={'skill':{'sourceUrl':'https://person:pass@example.org/a.git?x=1'}}))
    assert locked['source']['evidence']=='skill-lock' and locked['source']['url']=='https://example.org/a.git'
    assert resolve_skill(skill,hints=ProvenanceHints(lock={}))['origin']=='user'
    git = resolve_skill(skill,hints=ProvenanceHints())
    assert git['origin']=='unknown' and git['local_changes']=='unknown'
    assert git['source']['url'] is None and git['source']['ref'] is None
    (skill/'SKILL.md').write_text('edited');(skill/'new.txt').write_text('new')
    assert resolve_skill(skill,hints=ProvenanceHints())['local_changes']=='unknown'
    package = tmp_path/'package';package.mkdir()
    (package/'package.json').write_text('{"repository":{"url":"https://example.org/repo.git"}}')
    (package/'LICENSE').write_text('license')
    assert resolve_skill(package,hints=ProvenanceHints())['source']['evidence']=='package.json'
    (package/'package.json').unlink()
    license_only=resolve_skill(package,hints=ProvenanceHints(siblings={'package':'template'}))
    assert license_only['source']['kind']=='license_only' and license_only['source']['confidence']=='guess'
    (package/'LICENSE').unlink()
    derived=resolve_skill(package,hints=ProvenanceHints(siblings={'package':'template'}))
    assert derived['source']['evidence']=='tmpl-sibling' and derived['derived_from']=='template'
    assert resolve_skill(package,hints=ProvenanceHints())['origin']=='unknown'


def test_third_party_source_artifacts_and_heuristics_roundtrip(tmp_path):
    home=tmp_path/'home'
    roots={'claude':home/'.claude','codex':home/'.codex','shared':home/'.agents'}
    for root in roots.values():root.mkdir(parents=True)
    third=roots['shared']/'skills/diary';third.mkdir(parents=True)
    (roots['shared']/'.skill-lock.json').write_text(json.dumps({'skills':{'diary':{'sourceUrl':'https://example.org/owner/repo.git'}}}))
    body=('Example '+ 'API_'+'TOKEN'+'="example-only"\n').encode()
    (third/'SKILL.md').write_bytes(body);(third/'data.bin').write_bytes(b'\x00\xff');(third/'program.exe').write_bytes(b'program')
    (third/'node_modules').mkdir();(third/'node_modules/ignored.js').write_text('artifact')
    own=roots['claude']/'skills/diary';own.mkdir(parents=True)
    (own/'SKILL.md').write_text('changed own copy');(own/'program.exe').write_bytes(b'own executable')
    vendor=roots['codex']/'skills/.system/builtin';vendor.mkdir(parents=True)
    (vendor/'SKILL.md').write_text('vendor sentinel')
    out=tmp_path/'out';out.mkdir()
    plan=prepare_backup(home=home,config=load_config(tmp_path/'none.json',home=home),out=out,agents=frozenset(roots),environ={},software={'versions':{}},git_keys=[])
    entries=plan.writer.entries
    assert any(e['archive_path'].endswith('claude/main/skills/diary/program.exe') for e in entries)
    assert not any(e['archive_path'].endswith('shared/main/skills/diary/program.exe') for e in entries)
    assert not any('.system/' in e['archive_path'] or 'node_modules/' in e['archive_path'] for e in entries)
    report=json.loads(plan.writer._files['reports/skills.json'])
    assert report['summary']['third_party']==1 and report['summary']['unknown_source']==1 and report['summary']['vendor_builtin']==1
    assert report['copies'][0]['relation']=='diverged'
    assert len(next(s for s in report['skills'] if s['origin']=='third_party')['excluded'])==2
    coverage = {r['id']: r for r in plan.coverage['roots']}
    assert coverage['agents_home']['by_nature']['C']['files'] == 3
    assert coverage['agents_home']['by_nature']['C']['carried'] == 3
    assert coverage['agents_home']['by_nature']['E']['carried'] == 0
    assert coverage['claude_home']['by_nature']['A']['carried'] == 2
    assert coverage['codex_home']['by_nature']['C']['carried'] == 0
    apply_backup(plan)
    target=tmp_path/'target';(target/'.claude').mkdir(parents=True);(target/'.codex').mkdir()
    check=preflight(plan.writer.destination,home=target,config=load_config(tmp_path/'none2.json',home=target),environ={},processes=[])
    restore=plan_restore(check,state=tmp_path/'state',process_names=())
    apply_restore(restore,processes=[])
    assert (target/'.agents/skills/diary/SKILL.md').read_bytes()==body
    assert (target/'.claude/skills/diary/program.exe').read_bytes()==b'own executable'


def test_oversize_skill_excluded_before_read_and_expert_target_requires_opt_in(tmp_path, monkeypatch):
    home=tmp_path/'home';root=home/'.claude';skill=root/'skills/own';skill.mkdir(parents=True)
    source=skill/'large.bin';source.write_bytes(b'x'*40)
    writer=BundleWriter(tmp_path/'source.zip',source={'os':'windows'})
    from sync_core.machine import collect_skills as module
    original=module.read_source
    def guard(path,*args):
        assert path!=source
        return original(path,*args)
    monkeypatch.setattr(module,'read_source',guard)
    result=collect_skills(writer,home=home,config=load_config(tmp_path/'none.json',home=home),roots={'claude':root},agents=frozenset({'claude'}),os_name='windows',max_file_bytes=16)
    assert result.skills[0]['excluded'][0]['reason']=='too_large'
    sample=('sk-'+'A'*32).encode()
    data,flags=writer.prepare_content(sample,logical_path='claude:main/skills/own/SKILL.md',allow_secret=True)
    writer.add_file('files/claude/main/skills/own/SKILL.md',data,agent='claude',instance='main',kind='skills',logical_path='claude:main/skills/own/SKILL.md',flags=flags)
    writer.finalize()
    target=tmp_path/'target';(target/'.claude').mkdir(parents=True)
    config=load_config(tmp_path/'none2.json',home=target)
    with pytest.raises(BundleError,match='private content'):
        preflight(writer.destination,home=target,config=config,environ={},processes=[])
    config=replace(config,allow_secret_hit_paths=frozenset({target/'.claude/skills/own/SKILL.md'}))
    assert preflight(writer.destination,home=target,config=config,environ={},processes=[]).items[0].data==sample


def test_identical_same_named_skills_remain_three_independent_copies(tmp_path):
    from sync_core.machine.verify import verify
    from sync_core.machine.undo import undo
    home = tmp_path/'source'
    roots = {'claude': '.claude', 'codex': '.codex', 'shared': '.agents'}
    payloads = {'SKILL.md': '共同技能😀\n'.encode(), 'resources/data.bin': b'\x00\xffsame binary'}
    for branch in roots.values():
        for relative, body in payloads.items():
            source = home/branch/'skills/same'/relative
            source.parent.mkdir(parents=True, exist_ok=True); source.write_bytes(body)
    out = tmp_path/'out'; out.mkdir()
    plan = prepare_backup(home=home, config=load_config(tmp_path/'none.json', home=home), out=out,
                          agents=frozenset(roots), environ={}, software={'versions':{}}, git_keys=[])
    report = json.loads(plan.writer._files['reports/skills.json'])
    assert len(report['skills']) == 3 and len(report['copies']) == 1
    assert report['copies'][0]['relation'] == 'identical' and len(report['copies'][0]['members']) == 3
    entries = [e for e in plan.writer.entries if e['kind'] == 'skills']
    assert len(entries) == 6 and len({e['archive_path'] for e in entries}) == 6
    apply_backup(plan)
    target = tmp_path/'target'
    for branch in roots.values(): (target/branch).mkdir(parents=True)
    check = preflight(plan.writer.destination, home=target, config=load_config(tmp_path/'none2.json', home=target),
                      environ={}, processes=[])
    restore = plan_restore(check, state=tmp_path/'state', process_names=())
    result = apply_restore(restore, processes=[])
    assert result['writes'] == 6
    for branch in roots.values():
        for relative, body in payloads.items():
            assert (target/branch/'skills/same'/relative).read_bytes() == body
    verified = verify(check, restored=restore.restored, skipped=restore.skipped)
    assert sum(c['status'] == 'PASS' for c in verified.checks) == 6
    undo(tmp_path/'state', operation_id=Path(result['backup']).name, apply=True, processes=[])
    assert all(not (target/branch/'skills/same'/relative).exists() for branch in roots.values() for relative in payloads)


@pytest.mark.parametrize('failure', ['path_too_long', 'unreadable'])
def test_skill_file_failure_is_explicit_and_other_content_survives(tmp_path, monkeypatch, failure):
    home = tmp_path/'source'; skill = home/'.claude/skills/own'; skill.mkdir(parents=True)
    (skill/'SKILL.md').write_bytes(b'usable content')
    relative = ('folder-'+'a'*70+'/')*3+'data.txt' if failure == 'path_too_long' else 'unreadable.txt'
    bad = skill/relative; bad.parent.mkdir(parents=True, exist_ok=True); bad.write_bytes(b'skipped content')
    import sync_core.machine.collect_classified as module
    original = module._read
    def guard(path, boundary):
        if path == bad:
            if failure == 'path_too_long': pytest.fail('long member body was read')
            raise PermissionError('injected read failure')
        return original(path, boundary)
    monkeypatch.setattr(module, '_read', guard)
    out = tmp_path/'out'; out.mkdir()
    plan = prepare_backup(home=home, config=load_config(tmp_path/'none.json', home=home), out=out,
                          agents=frozenset({'claude'}), environ={}, software={'versions':{}}, git_keys=[])
    report = json.loads(plan.writer._files['reports/skills.json'])['skills'][0]
    assert report['carried'] == 'partial' and report['files'] == 1
    assert report['excluded'] == [{'path':relative, 'reason':failure, 'size':15}]
    assert sum(e['reason'] == failure for e in plan.exclusions) == 1
    assert any(e['archive_path'].endswith('own/SKILL.md') for e in plan.writer.entries)
    apply_backup(plan)
    target = tmp_path/'target'; (target/'.claude').mkdir(parents=True)
    check = preflight(plan.writer.destination, home=target, config=load_config(tmp_path/'none2.json', home=target), environ={}, processes=[])
    restore = plan_restore(check, state=tmp_path/'state', process_names=())
    apply_restore(restore, processes=[])
    assert (target/'.claude/skills/own/SKILL.md').read_bytes() == b'usable content'
    assert not (target/'.claude/skills/own'/relative).exists()


@pytest.mark.parametrize('child_first', [False, True])
def test_nested_project_skill_has_one_owner_and_restores_to_child(tmp_path, child_first):
    from sync_core.machine.paths import RootMap
    from sync_core.machine.collect_tier1 import project_id
    home = tmp_path/'home'; (home/'.workbuddy-ai').mkdir(parents=True)
    parent = tmp_path/'parent'; child = parent/'child'
    for folder, body in [(parent, b'parent skill'), (child, b'child skill')]:
        source = folder/'.workbuddy-ai/skills/same/SKILL.md'
        source.parent.mkdir(parents=True, exist_ok=True); source.write_bytes(body)
    config_file = tmp_path/'config.json'
    projects = [child, parent] if child_first else [parent, child]
    config_file.write_text(json.dumps({'core_projects':[str(p) for p in projects]}))
    out = tmp_path/'out'; out.mkdir()
    plan = prepare_backup(home=home, config=load_config(config_file, home=home), out=out,
                          agents=frozenset({'workbuddy-ai'}), environ={}, os_name='windows', software={'versions':{}}, git_keys=[])
    entries = [e for e in plan.writer.entries if e['kind'] == 'skills']
    assert len(entries) == 2
    assert {e['project_id'] for e in entries} == {project_id(p, 'windows') for p in projects}
    assert all('/child/' not in e['archive_path'] for e in entries)
    apply_backup(plan)
    target = tmp_path/'target'; (target/'.workbuddy-ai').mkdir(parents=True)
    new_parent = tmp_path/'new-parent'; new_child = new_parent/'child'; new_child.mkdir(parents=True)
    mapper = RootMap(((str(parent), str(new_parent)), (str(child), str(new_child))))
    check = preflight(plan.writer.destination, home=target, config=load_config(tmp_path/'none.json', home=target),
                      environ={}, processes=[], os_name='windows', root_map=mapper)
    restore = plan_restore(check, state=tmp_path/'state', process_names=(), workbuddy_files=True)
    result = apply_restore(restore, processes=[])
    assert result['writes'] == 2
    assert (new_parent/'.workbuddy-ai/skills/same/SKILL.md').read_bytes() == b'parent skill'
    assert (new_child/'.workbuddy-ai/skills/same/SKILL.md').read_bytes() == b'child skill'


@pytest.mark.parametrize('failure', ['enumeration_failed', 'metadata_unreadable'])
def test_skill_directory_and_metadata_failures_are_explicit(tmp_path, monkeypatch, failure):
    from _agent_homes import ReadTracker
    import os
    home = tmp_path/'home'; skill = home/'.claude/skills/own'; skill.mkdir(parents=True)
    (skill/'SKILL.md').write_bytes(b'usable')
    bad = skill/'blocked/hidden.txt' if failure == 'enumeration_failed' else skill/'metadata.txt'
    bad.parent.mkdir(parents=True, exist_ok=True); bad.write_bytes(b'never read')
    if failure == 'enumeration_failed':
        original = os.scandir
        def scandir(path):
            if isinstance(path, (str, Path)) and Path(path) == bad.parent:
                raise PermissionError(13, 'injected enumeration failure', str(bad.parent))
            return original(path)
        monkeypatch.setattr(os, 'scandir', scandir)
    else:
        original = Path.stat
        def stat(path, *args, **kwargs):
            if path == bad and kwargs.get('follow_symlinks', True):
                raise PermissionError(13, 'injected metadata failure', str(bad))
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'stat', stat)
    tracker = ReadTracker(monkeypatch)
    out = tmp_path/'out'; out.mkdir()
    plan = prepare_backup(home=home, config=load_config(tmp_path/'none.json', home=home), out=out,
                          agents=frozenset({'claude'}), environ={}, software={'versions':{}}, git_keys=[])
    record = json.loads(plan.writer._files['reports/skills.json'])['skills'][0]
    assert record['carried'] == 'partial' and record['files'] == 1
    assert record['excluded'][0]['reason'] == failure and record['excluded'][0]['size'] is None
    assert any(e['reason'] == failure for e in plan.exclusions) and not tracker.touched([bad])
    assert not plan.coverage['totals']['complete']
    apply_backup(plan)


def test_unenumerable_skill_container_is_reported_without_body_reads(tmp_path, monkeypatch):
    from _agent_homes import ReadTracker
    import os
    home = tmp_path/'home'; container = home/'.claude/skills'
    source = container/'own/SKILL.md'; source.parent.mkdir(parents=True); source.write_bytes(b'never read')
    original = os.scandir
    def scandir(path):
        if isinstance(path, (str, Path)) and Path(path) == container:
            raise PermissionError(13, 'injected enumeration failure', str(container))
        return original(path)
    monkeypatch.setattr(os, 'scandir', scandir)
    tracker = ReadTracker(monkeypatch)
    out = tmp_path/'out'; out.mkdir()
    plan = prepare_backup(home=home, config=load_config(tmp_path/'none.json', home=home), out=out,
                          agents=frozenset({'claude'}), environ={}, software={'versions':{}}, git_keys=[])
    assert not tracker.touched([source]) and not any(e['kind'] == 'skills' for e in plan.writer.entries)
    assert any(e['reason'] == 'enumeration_failed' for e in plan.exclusions)
    assert not plan.coverage['totals']['complete']
