from dataclasses import replace
import json
import subprocess

import pytest

from sync_core.machine.backup import prepare_backup, apply_backup
from sync_core.machine.collect_env import collect_environment, snapshot
from sync_core.machine.bundle import BundleWriter
from sync_core.machine.config import load_config
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore, apply_restore


def test_secret_values_are_never_accessed():
    class NameOnly(dict):
        def __getitem__(self, name):
            if name == 'OPENAI_API_KEY':
                raise AssertionError('secret-name value queried')
            return super().__getitem__(name)
    safe, names = snapshot(NameOnly(OPENAI_API_KEY=object(), AI_TEST='yes', PATH='runtime'), frozenset())
    assert safe == {'AI_TEST': 'yes'} and names == ('OPENAI_API_KEY',)


def test_environment_export_roundtrip_and_powershell_syntax(tmp_path):
    home = tmp_path/'source'; (home/'.claude').mkdir(parents=True)
    out = tmp_path/'out'; out.mkdir()
    config = replace(load_config(tmp_path/'missing.json', home=home), env_include=frozenset({'EXTRA_SETTING', 'CUSTOM_TOKEN'}))
    sample = 'not-to-export'
    table = {'AI_QUOTE': "a'b`$()\nline\r\n", 'OPENAI_BASE_URL': 'https://example.org',
             'API_TIMEOUT_MS': '5000', 'EXTRA_SETTING': '%USERPROFILE%/data', 'Path': 'runtime',
             'OPENAI_API_KEY': sample, 'CUSTOM_TOKEN': sample,
             'HTTPS_PROXY': 'https://person:pass@example.org'}
    plan = prepare_backup(home=home, config=config, out=out, environ={}, user_environment=table,
                          agents=frozenset({'claude'}), software={'versions':{}}, git_keys=[])
    assert sample.encode() not in b''.join(plan.writer._files.values())
    assert b'person:pass' not in b''.join(plan.writer._files.values())
    login = plan.writer._files['reports/login-checklist.md'].decode()
    assert all(name in login for name in ('OPENAI_API_KEY', 'CUSTOM_TOKEN', 'HTTPS_PROXY'))
    entry = next(e for e in plan.writer.entries if e['kind']=='env_fields')
    fields = json.loads(plan.writer._files[entry['archive_path']])['fields']
    assert set(fields) == {'AI_QUOTE', 'OPENAI_BASE_URL', 'API_TIMEOUT_MS', 'EXTRA_SETTING'}
    observed = next(f for f in plan.coverage['fields'] if f['source'] == 'user_env')
    assert set(observed['confirm']) == set(fields)
    assert set(observed['never']) == {'OPENAI_API_KEY', 'CUSTOM_TOKEN', 'HTTPS_PROXY', 'Path'}
    apply_backup(plan)
    target = tmp_path/'target'; target.mkdir()
    report = tmp_path/'reports'
    check = preflight(plan.writer.destination, home=target, config=load_config(tmp_path/'missing2.json',home=target),
                      environ={}, processes=[], report_dir=report)
    restore = plan_restore(check,state=tmp_path/'state',process_names=())
    apply_restore(restore,processes=[])
    script = report/'restore-env.ps1'
    assert "a''b`$()" in script.read_text(encoding='utf-8-sig')
    # Parse only: never invoke the generated script or write user registry.
    literal_path = str(script).replace("'", "''")
    command = "$tokens=$null; $issues=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('" + literal_path + "',[ref]$tokens,[ref]$issues); if($issues.Count){exit 1}"
    result = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert not (target/'.claude').exists()
    table['AI_QUOTE'] = 'changed'
    assert not plan.verify_sources_unchanged()


def test_synthetic_home_does_not_read_registry_and_include_validation(tmp_path, monkeypatch):
    import sync_core.machine.collect_env as module
    monkeypatch.setattr(module, 'registry_environment', lambda _: pytest.fail('real registry queried'))
    config = load_config(tmp_path/'missing.json',home=tmp_path)
    result = collect_environment(BundleWriter(tmp_path/'out.zip',source={'os':'windows'}),home=tmp_path,
                                 config=config,os_name='windows')
    assert result.verify_sources_unchanged()
    path = tmp_path/'config.json'; path.write_text('{"env_include":["bad-name"]}')
    with pytest.raises(ValueError, match='env_include'):
        load_config(path,home=tmp_path)
