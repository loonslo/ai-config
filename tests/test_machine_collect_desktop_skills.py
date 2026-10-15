import json
import zipfile
import pytest

from sync_core.machine.backup import prepare_backup, apply_backup
from sync_core.machine.config import load_config
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore, apply_restore


def test_multilevel_accounts_export_distinct_same_named_skills(tmp_path, monkeypatch):
    home = tmp_path/'home'; (home/'.claude').mkdir(parents=True)
    desktop = home/'AppData/Roaming/Claude'
    roots = []
    for account, organization, list_format, body in [('account1','org1',False,b'first'),('account2','org2',True,b'second')]:
        root = desktop/'local-agent-mode-sessions/skills-plugin'/account/organization
        roots.append(root)
        for name in ('same','builtin'):
            (root/'skills'/name).mkdir(parents=True)
            (root/'skills'/name/'SKILL.md').write_bytes(body if name=='same' else b'vendor sentinel')
        (root/'skills/same/data.bin').write_bytes(b'\x00\xff')
        skills = {'same':{'creatorType':'user'},'builtin':{'creatorType':'anthropic'}}
        if list_format:
            skills = [{'name':k,**v} for k,v in skills.items()]
        (root/'manifest.json').write_text(json.dumps({'skills':skills}),encoding='utf-8')
    # Guard only the new collector's vendor body reads; source fingerprints are also checked.
    from sync_core.machine import collect_desktop_skills as module
    original = module.read_source
    def guard(path, *args):
        assert 'builtin' not in path.parts
        return original(path,*args)
    monkeypatch.setattr(module,'read_source',guard)
    out = tmp_path/'out'; out.mkdir()
    plan = prepare_backup(home=home,config=load_config(tmp_path/'missing.json',home=home),out=out,
                          agents=frozenset({'claude'}),environ={},software={'versions':{}},git_keys=[])
    skills = [e for e in plan.writer.entries if e['instance']=='desktop' and e['kind']=='skills']
    assert len(skills)==4 and len({e['conflict_group'] for e in skills})==2
    assert not any('builtin' in e['archive_path'] for e in skills)
    report = json.loads(plan.writer._files['reports/account-skills.json'])
    assert len(report['skills'])==4
    assert sum(s['origin']=='vendor_builtin' and s['files']==0 for s in report['skills'])==2
    covered = next(r for r in plan.coverage['roots'] if r['id'] == 'claude_desktop')
    assert covered['by_nature']['A'] == {'files': 4, 'bytes': 15, 'carried': 4}
    assert covered['by_nature']['C']['files'] == 4 and covered['by_nature']['C']['carried'] == 0
    assert covered['unclassified']['count'] == 0 and covered['complete']
    apply_backup(plan)
    target = tmp_path/'target'; target.mkdir()
    reports = tmp_path/'reports'
    check = preflight(plan.writer.destination,home=target,config=load_config(tmp_path/'none.json',home=target),
                      environ={},processes=[],report_dir=reports)
    restore = plan_restore(check,state=tmp_path/'state',process_names=())
    assert not restore.changes
    apply_restore(restore,processes=[])
    for alias, body in [('a0001',b'first'),('a0002',b'second')]:
        with zipfile.ZipFile(reports/'account-skills'/alias/'same.zip') as archive:
            assert set(archive.namelist())=={'same/SKILL.md','same/data.bin'}
            assert archive.read('same/SKILL.md')==body
    assert not (target/'AppData').exists() and not (target/'.claude').exists()
    (roots[0]/'manifest.json').write_text('{"skills":{}}')
    assert not plan.verify_sources_unchanged()


def test_unknown_creator_and_manifest_traversal_are_not_carried(tmp_path):
    home = tmp_path/'home'; (home/'.claude').mkdir(parents=True)
    root = home/'AppData/Roaming/Claude/local-agent-mode-sessions/skills-plugin/a/o'
    (root/'skills/unknown').mkdir(parents=True)
    (root/'skills/unknown/SKILL.md').write_text('unknown')
    (root/'manifest.json').write_text(json.dumps({'skills':{'unknown':{'creatorType':'other'},'../escape':{'creatorType':'user'}}}))
    out = tmp_path/'out'; out.mkdir()
    plan = prepare_backup(home=home,config=load_config(tmp_path/'none.json',home=home),out=out,
                          agents=frozenset({'claude'}),environ={},software={'versions':{}},git_keys=[])
    assert not any(e['instance']=='desktop' for e in plan.writer.entries)
    covered = next(r for r in plan.coverage['roots'] if r['id'] == 'claude_desktop')
    assert covered['unclassified']['count'] == 1 and covered['by_nature']['C']['files'] == 1


def test_account_skill_artifacts_are_pruned_and_never_read(tmp_path, monkeypatch):
    from _agent_homes import ReadTracker
    home = tmp_path/'home'; (home/'.claude').mkdir(parents=True)
    root = home/'AppData/Roaming/Claude/local-agent-mode-sessions/skills-plugin/a/o'
    skill = root/'skills/own'; skill.mkdir(parents=True)
    (root/'manifest.json').write_text(json.dumps({'skills': {'own': {'creatorType': 'user'}}}))
    (skill/'SKILL.md').write_bytes(b'own')
    (skill/'program.exe').write_bytes(b'own executable')
    pyc = skill/'code.pyc'; pyc.write_bytes(b'artifact')
    node = skill/'node_modules/deep/ignored.js'; node.parent.mkdir(parents=True); node.write_bytes(b'artifact')
    marker = skill/'nested/mode_migration.json'; marker.parent.mkdir(); marker.write_bytes(b'artifact')
    tracker = ReadTracker(monkeypatch)
    out = tmp_path/'out'; out.mkdir()
    plan = prepare_backup(home=home, config=load_config(tmp_path/'none.json', home=home), out=out,
                          agents=frozenset({'claude'}), environ={}, software={'versions':{}}, git_keys=[])
    assert not tracker.touched([pyc, node, marker])
    carried = [e for e in plan.writer.entries if e['instance'] == 'desktop' and e['kind'] == 'skills']
    assert len(carried) == 2 and any(e['archive_path'].endswith('program.exe') for e in carried)
    covered = next(r for r in plan.coverage['roots'] if r['id'] == 'claude_desktop')
    assert covered['by_nature']['A']['carried'] == 2 and covered['by_nature']['E']['carried'] == 0
    assert any(p['rule_id'] == 'SK-05' and p['path'].endswith('node_modules') for p in covered['pruned'])


@pytest.mark.parametrize('failure', ['path_too_long', 'unreadable'])
def test_account_skill_file_failure_retains_usable_export(tmp_path, monkeypatch, failure):
    home = tmp_path/'home'; (home/'.claude').mkdir(parents=True)
    root = home/'AppData/Roaming/Claude/local-agent-mode-sessions/skills-plugin/a/o'
    skill = root/'skills/own'; skill.mkdir(parents=True)
    (root/'manifest.json').write_text(json.dumps({'skills': {'own': {'creatorType': 'user'}}}))
    (skill/'SKILL.md').write_bytes(b'usable')
    relative = ('folder-'+'a'*70+'/')*3+'data.txt' if failure == 'path_too_long' else 'unreadable.txt'
    bad = skill/relative; bad.parent.mkdir(parents=True, exist_ok=True); bad.write_bytes(b'skipped')
    import sync_core.machine.collect_classified as module
    original = module._read
    def guard(path, boundary):
        if path == bad:
            if failure == 'path_too_long': pytest.fail('long account member body read')
            raise PermissionError('injected read failure')
        return original(path, boundary)
    monkeypatch.setattr(module, '_read', guard)
    out = tmp_path/'out'; out.mkdir()
    plan = prepare_backup(home=home, config=load_config(tmp_path/'none.json', home=home), out=out,
                          agents=frozenset({'claude'}), environ={}, software={'versions':{}}, git_keys=[])
    report = json.loads(plan.writer._files['reports/account-skills.json'])['skills'][0]
    assert report['carried'] == 'partial' and report['files'] == 1
    assert report['excluded'][0]['path'] == relative and report['excluded'][0]['reason'] == failure
    assert any(e['reason'] == failure for e in plan.exclusions)
    apply_backup(plan)
    target = tmp_path/'target'; target.mkdir()
    reports = tmp_path/'reports'
    check = preflight(plan.writer.destination, home=target, config=load_config(tmp_path/'none2.json', home=target),
                      environ={}, processes=[], report_dir=reports)
    restore = plan_restore(check, state=tmp_path/'state', process_names=())
    apply_restore(restore, processes=[])
    with zipfile.ZipFile(reports/'account-skills/a0001/own.zip') as archive:
        assert archive.namelist() == ['own/SKILL.md'] and archive.read('own/SKILL.md') == b'usable'


@pytest.mark.parametrize('failure', ['root_enumeration', 'account_enumeration', 'skill_enumeration',
                                     'nested_enumeration', 'file_stat', 'skill_stat', 'manifest_stat'])
def test_account_source_permission_failures_are_reported(tmp_path, monkeypatch, failure):
    import os
    from pathlib import Path
    from _agent_homes import ReadTracker
    home = tmp_path/'home'; (home/'.claude').mkdir(parents=True)
    root = home/'AppData/Roaming/Claude/local-agent-mode-sessions/skills-plugin'
    account = root/'a'; folder = account/'o'; skill = folder/'skills/own'
    nested = skill/'nested'; nested.mkdir(parents=True)
    manifest = folder/'manifest.json'
    manifest.write_text(json.dumps({'skills': {'own': {'creatorType': 'user'}}}))
    usable = skill/'SKILL.md'; usable.write_bytes(b'usable')
    bad = nested/'data.txt'; bad.write_bytes(b'unreadable sentinel')
    tracker = ReadTracker(monkeypatch)
    if failure.endswith('enumeration'):
        blocked = {'root_enumeration':root, 'account_enumeration':account,
                   'skill_enumeration':skill, 'nested_enumeration':nested}[failure]
        original_scan = os.scandir
        def scan(path):
            if Path(path) == blocked:
                raise PermissionError(13, 'synthetic enumeration denied', str(blocked))
            return original_scan(path)
        monkeypatch.setattr(os, 'scandir', scan)
    else:
        blocked = {'file_stat':bad, 'skill_stat':skill, 'manifest_stat':manifest}[failure]
        original_stat = Path.stat
        def metadata(path, *args, **kwargs):
            if path == blocked:
                raise PermissionError(13, 'synthetic metadata denied', str(blocked))
            return original_stat(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'stat', metadata)
    out = tmp_path/'out'; out.mkdir()
    plan = prepare_backup(home=home, config=load_config(tmp_path/'none.json', home=home), out=out,
                          agents=frozenset({'claude'}), environ={}, software={'versions':{}}, git_keys=[])
    reason = 'enumeration_failed' if failure.endswith('enumeration') else 'metadata_unreadable'
    assert any(e['reason'] == reason and e['logical_path'].startswith('claude:desktop/') for e in plan.exclusions)
    assert not tracker.touched([bad])
    assert not plan.coverage['totals']['complete']
    report = json.loads(plan.writer._files['reports/account-skills.json'])['skills']
    if failure in {'nested_enumeration', 'file_stat', 'skill_enumeration', 'skill_stat'}:
        assert len(report) == 1 and report[0]['carried'] == 'partial'
        assert report[0]['excluded'][0]['reason'] == reason and report[0]['excluded'][0]['size'] is None
    if failure in {'nested_enumeration', 'file_stat'}:
        assert report[0]['files'] == 1
        apply_backup(plan)
        target = tmp_path/'target'; target.mkdir()
        reports = tmp_path/'reports'
        check = preflight(plan.writer.destination, home=target, config=load_config(tmp_path/'none2.json', home=target),
                          environ={}, processes=[], report_dir=reports)
        restore = plan_restore(check, state=tmp_path/'state', process_names=())
        apply_restore(restore, processes=[])
        with zipfile.ZipFile(reports/'account-skills/a0001/own.zip') as archive:
            assert archive.namelist() == ['own/SKILL.md'] and archive.read('own/SKILL.md') == b'usable'
