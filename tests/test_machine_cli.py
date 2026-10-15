import importlib.util
import json
from pathlib import Path
import pytest

from test_machine_preflight import fixture_bundle


@pytest.mark.parametrize('as_json', [False, True])
@pytest.mark.parametrize('override', [False, True])
def test_expert_cli_full_lifecycle_output_hygiene(tmp_path, monkeypatch, capsys, as_json, override):
    import scripts.machine as cli
    import sync_core.machine.apply as apply_module
    import sync_core.machine.undo as undo_module
    from sync_core.machine.bundle import read_bundle

    email = 'person@example.org'
    sample = 'sk-' + 'A' * 32
    source = tmp_path / email / 'source'
    target = tmp_path / email / 'target'
    for home in (source, target):
        (home / '.codex').mkdir(parents=True)
    payload = ('Contact ' + email + '\nFixture ' + sample + '\n').encode()
    (source / '.codex/AGENTS.md').write_bytes(payload)
    output = tmp_path / email / 'output'
    output.mkdir()
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'allow_secret_hit_paths':
        [str(source / '.codex/AGENTS.md'), str(target / '.codex/AGENTS.md')] if override else []}), encoding='utf-8')
    current = [source]
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: current[0]))
    monkeypatch.setattr(cli, 'default_state_path', lambda **kwargs: target / 'state')
    monkeypatch.setattr(cli, 'software_inventory', lambda **kwargs: {'versions': {}})
    original_backup = cli.prepare_backup
    monkeypatch.setattr(cli, 'prepare_backup', lambda **kwargs: original_backup(
        **kwargs, environ={}, software={'versions': {}}, git_keys=[], user_environment={}))
    original_preflight = cli.preflight
    monkeypatch.setattr(cli, 'preflight', lambda *args, **kwargs: original_preflight(
        *args, **kwargs, environ={}, processes=[]))
    monkeypatch.setattr(apply_module, 'running_apps', lambda *args, **kwargs: [])
    monkeypatch.setattr(undo_module, 'running_apps', lambda *args, **kwargs: [])
    flag = ['--json'] if as_json else []

    def run(arguments, expected):
        assert cli.main([*arguments, *flag]) == expected
        captured = capsys.readouterr()
        assert email not in captured.out + captured.err
        assert sample not in captured.out + captured.err
        if as_json:
            return json.loads(captured.out)

    backup = ['backup', '--config', str(config), '--out', str(output), '--agents', 'codex']
    run(backup, 3)
    assert list(output.iterdir()) == []
    run([*backup, '--apply'], 0)
    bundle, = output.glob('*.zip')
    manifest, files = read_bundle(bundle)
    expected = payload if override else payload.replace(sample.encode(), b'<REDACTED>')
    assert files['files/codex/main/AGENTS.md'] == expected
    assert manifest['schema_version'] == 2
    current[0] = target
    common = ['--bundle', str(bundle), '--config', str(config), '--agents', 'codex']
    run(['preflight', *common], 3)
    run(['restore', *common], 3)
    assert not (target / '.codex/AGENTS.md').exists()
    run(['restore', *common, '--apply'], 0)
    assert (target / '.codex/AGENTS.md').read_bytes() == expected
    run(['verify', *common], 0)
    run(['undo', '--index', '1'], 3)
    run(['undo', '--index', '1', '--apply'], 0)
    assert not (target / '.codex/AGENTS.md').exists()
    assert (source / '.codex/AGENTS.md').read_bytes() == payload


def test_expert_cli_preview_apply_verify_undo_in_isolated_home(tmp_path,monkeypatch,capsys):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    spec=importlib.util.spec_from_file_location('machine_cli',Path(__file__).resolve().parents[1]/'scripts/machine.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:home))
    monkeypatch.setattr(module,'software_inventory',lambda **kwargs:{'versions':{'python':'3.14.0'}})
    original=module.preflight
    monkeypatch.setattr(module,'preflight',lambda *args,**kwargs:original(*args,**kwargs,processes=[]))
    import sync_core.machine.apply as apply_module
    import sync_core.machine.undo as undo_module
    monkeypatch.setattr(apply_module,'running_apps',lambda *args,**kwargs:[])
    monkeypatch.setattr(undo_module,'running_apps',lambda *args,**kwargs:[])
    old,new=mapper.rules[0]
    common=['--bundle',str(bundle),'--root-map',old+'='+new,'--agents','codex','--json']
    assert module.main(['preflight',*common])==4
    check=json.loads(capsys.readouterr().out)
    assert not (home/'.codex/AGENTS.md').exists()
    assert module.main(['restore',*common])==4
    capsys.readouterr()
    assert not (home/'.codex/AGENTS.md').exists()
    assert module.main(['restore',*common,'--codex-trust','--confirm-trust',check['trust_list_hash'],'--apply'])==0
    restored=json.loads(capsys.readouterr().out)
    assert restored['mode']=='applied' and (home/'.codex/AGENTS.md').exists()
    assert module.main(['verify',*common])==0
    assert not any(item['status']=='FAIL' for item in json.loads(capsys.readouterr().out)['checks'])
    assert module.main(['undo','--index','1','--json'])==3
    capsys.readouterr()
    assert module.main(['undo','--index','1','--apply','--json'])==0
    capsys.readouterr()
    assert not (home/'.codex/AGENTS.md').exists()


def test_unapproved_restore_manifest_cannot_open_protected_target(tmp_path,monkeypatch):
    from _agent_homes import ReadTracker,SENTINEL
    from sync_core.machine.bundle import BundleWriter
    from sync_core.machine.config import load_config
    from sync_core.machine.preflight import preflight
    import pytest
    home=tmp_path/'home';(home/'.codex').mkdir(parents=True)
    protected=home/'.codex/auth.json';protected.write_text(SENTINEL,encoding='utf-8')
    archive=tmp_path/'malicious.zip'
    writer=BundleWriter(archive,source={'os':'windows'})
    writer.add_file('files/codex/main/auth.json',b'harmless content',agent='codex',instance='main',kind='rules',logical_path='codex:main/auth.json')
    writer.finalize()
    tracker=ReadTracker(monkeypatch)
    with pytest.raises(ValueError,match='catalog'):
        preflight(archive,home=home,config=load_config(tmp_path/'absent.json',home=home),environ={},processes=[])
    assert tracker.touched([protected])==[]
