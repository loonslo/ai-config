"""Explicit conflict decisions, recoverable overwrites and meaningful summaries."""
import json
from pathlib import Path
import tomllib

import pytest

from sync_core.application.machine_protocol import MachineProtocol
from sync_core.machine.apply import plan_restore, apply_restore
from sync_core.machine.bundle import BundleWriter
from sync_core.machine.config import load_config
from sync_core.machine.preflight import preflight
from sync_core.machine.verify import verify
from sync_core.transaction import write_file
from test_machine_desktop import preview, apply
from test_machine_preflight import fixture_bundle


@pytest.fixture(autouse=True)
def isolated_processes(monkeypatch):
    monkeypatch.setattr('sync_core.machine.procs.process_names', lambda: [])


def existing_target(tmp_path):
    bundle, home, _, _, mapper = fixture_bundle(tmp_path)
    originals = {home / '.codex/AGENTS.md': b'Local rules before restore.\n',
                 home / '.codex/config.toml': b'# local comment\nmodel_reasoning_effort = "low"\n[local_extension]\nx = 42\n'}
    for path, data in originals.items():
        path.write_bytes(data)
    protocol = MachineProtocol(tmp_path / 'device.json', home=home, environ={})
    params = {'bundle': str(bundle), 'agents': ['codex'],
              'root_map': [{'from': old, 'to': new} for old, new in mapper.rules]}
    return protocol, params, originals


def test_overwrite_requires_choice_backs_up_before_writing_and_undoes(tmp_path, monkeypatch):
    protocol, params, originals = existing_target(tmp_path)
    pending = preview(protocol, 'machine_restore', **params)
    assert not pending['can_apply'] and 'plan_id' not in pending
    assert pending['result']['pending_conflicts'] == 2
    assert all(path.read_bytes() == data for path, data in originals.items())
    params['conflict_choices'] = {v['entry_id']: 'overwrite' for v in pending['result']['conflicts']}
    planned = preview(protocol, 'machine_restore', **params)
    assert planned['can_apply']
    observed = []

    def assert_backup_then_write(path, data):
        if path in originals:
            manifests = list((protocol.state / 'backups').glob('*/manifest.json'))
            assert len(manifests) == 1
            records = json.loads(manifests[0].read_text(encoding='utf-8'))
            record = next(v for v in records if v['path'] == str(path))
            assert (manifests[0].parent / record['file']).read_bytes() == originals[path]
            observed.append(path)
        write_file(path, data)

    monkeypatch.setattr('sync_core.machine.apply.write_file', assert_backup_then_write)
    result = apply(protocol, planned)
    assert result['status'] == 'applied'
    assert set(observed) == set(originals)
    config = next(path for path in originals if path.name == 'config.toml')
    raw = tomllib.loads(config.read_text(encoding='utf-8'))
    assert raw['model_reasoning_effort'] == 'high' and raw['local_extension']['x'] == 42
    assert config.read_text(encoding='utf-8').startswith('# local comment\n')
    assert not list(protocol.home.rglob('*.from-bundle'))
    assert Path(result['result']['backup']).is_dir()
    assert not any(v['status'] == 'FAIL' for v in result['result']['verification']['checks'])
    history = preview(protocol, 'machine_history')['result']['operations']
    undo_plan = preview(protocol, 'machine_undo', operation_id=history[0]['operation_id'])
    assert apply(protocol, undo_plan)['status'] == 'applied'
    assert all(path.read_bytes() == data for path, data in originals.items())


def test_keep_skips_different_content_without_alternate_files(tmp_path):
    protocol, params, originals = existing_target(tmp_path)
    pending = preview(protocol, 'machine_restore', **params)
    params['conflict_choices'] = {v['entry_id']: 'keep' for v in pending['result']['conflicts']}
    result = apply(protocol, preview(protocol, 'machine_restore', **params))
    assert result['status'] == 'applied'
    assert all(path.read_bytes() == data for path, data in originals.items())
    assert not list(protocol.home.rglob('*.from-bundle'))
    verification = result['result']['verification']
    assert verification['counts']['KEPT'] == 2
    assert all(v['agent'] != 'codex' for v in verification['questions'])


def test_pending_core_plan_rejects_apply_and_unknown_choices(tmp_path):
    bundle, home, _, config, mapper = fixture_bundle(tmp_path)
    (home / '.codex/AGENTS.md').write_bytes(b'Existing local rules')
    check = preflight(bundle, home=home, config=config, root_map=mapper, environ={}, processes=[])
    plan = plan_restore(check, state=home / 'state', process_names=(), conflict_choices={})
    with pytest.raises(ValueError, match='choose overwrite or keep'):
        apply_restore(plan, processes=[])
    assert not (home / 'state').exists()
    with pytest.raises(ValueError, match='invalid conflict choice'):
        plan_restore(check, state=home / 'state', process_names=(), conflict_choices={'unknown': 'overwrite'})


def test_overwrite_failure_rolls_back_original_files(tmp_path):
    protocol, params, originals = existing_target(tmp_path)
    bundle = Path(params['bundle'])
    config = load_config(tmp_path / 'missing.json', home=protocol.home)
    from sync_core.machine.paths import RootMap
    mapper = RootMap(tuple((v['from'], v['to']) for v in params['root_map']), 'windows', 'windows')
    check = preflight(bundle, home=protocol.home, config=config, root_map=mapper,
                      agents=frozenset({'codex'}), environ={}, processes=[])
    pending = plan_restore(check, state=protocol.state, process_names=(), conflict_choices={})
    plan = plan_restore(check, state=protocol.state, process_names=(),
                        conflict_choices={v['entry_id']: 'overwrite' for v in pending.conflicts})
    calls = []
    def fail_second(path, data):
        calls.append(path)
        if len(calls) == 2:
            raise OSError('injected overwrite failure')
        write_file(path, data)
    with pytest.raises(OSError, match='injected overwrite failure'):
        apply_restore(plan, processes=[], writer=fail_second)
    assert all(path.read_bytes() == data for path, data in originals.items())
    assert all(not path.exists() for path in plan.changes if path not in originals)


def test_trust_overwrite_requires_separate_confirmation(tmp_path):
    bundle, home, project, config, mapper = fixture_bundle(tmp_path)
    path = str(project).replace('\\', '/').lower()
    target = home / '.codex/config.toml'
    target.write_text(f"[projects.'{path}']\ntrust_level = 'untrusted'\n", encoding='utf-8')
    check = preflight(bundle, home=home, config=config, root_map=mapper, environ={}, processes=[])
    trust = next(item for item in check.items if item.entry['kind'] == 'trust_fields' and item.entry['agent'] == 'codex')
    settings = next(item for item in check.items if item.entry['kind'] == 'settings_fields' and item.entry['agent'] == 'codex')
    choices = {trust.entry['id']: 'overwrite', settings.entry['id']: 'overwrite'}
    not_confirmed = plan_restore(check, state=home / 'state', process_names=(), conflict_choices=choices)
    apply_restore(not_confirmed, processes=[])
    assert tomllib.loads(target.read_text(encoding='utf-8'))['projects'][path]['trust_level'] == 'untrusted'
    check = preflight(bundle, home=home, config=config, root_map=mapper, environ={}, processes=[])
    confirmed = plan_restore(check, state=home / 'state', process_names=(), conflict_choices=choices,
                             codex_trust=True, confirm_trust=check.trust_list_hash)
    apply_restore(confirmed, processes=[])
    assert tomllib.loads(target.read_text(encoding='utf-8'))['projects'][path]['trust_level'] == 'trusted'


def summary_fixture(tmp_path):
    archive = tmp_path / 'summary.zip'
    writer = BundleWriter(archive, source={'os': 'windows'})
    writer.add_file('files/codex/main/config.fields.json', json.dumps({'fields': {
        'model_reasoning_effort': 'high', 'personality': 'friendly', 'model': 'backup-model'}}).encode(),
        agent='codex', instance='main', kind='settings_fields', logical_path='codex:main/config.toml', mode='fields')
    writer.add_file('files/codex/main/AGENTS.md', b'<!-- ai-config:begin -->\n```text\nIgnored code block instruction.\n```\n- Always explain the concrete decision before editing.\n',
                    agent='codex', instance='main', kind='rules', logical_path='codex:main/AGENTS.md')
    for index in range(4):
        writer.add_file(f'files/codex/main/skills/demo/{index}.md', f'Skill {index}'.encode(),
                        agent='codex', instance='main', kind='skills_text', logical_path=f'codex:main/skills/demo/{index}.md')
    for index in range(3):
        writer.add_file(f'files/workbuddy-ai/workbuddy-ai/memory/{index}.md', b'Safe note',
                        agent='workbuddy-ai', instance='workbuddy-ai', kind='memory', logical_path=f'workbuddy-ai:workbuddy-ai/memory/{index}.md')
    writer.finalize()
    home = tmp_path / 'home'; (home / '.codex').mkdir(parents=True)
    target = home / '.codex/config.toml'
    target.write_text('model_reasoning_effort = "low"\nmodel = "local-model"\n', encoding='utf-8')
    config = load_config(tmp_path / 'missing.json', home=home)
    check = preflight(archive, home=home, config=config, agents=frozenset({'codex'}), environ={}, processes=[])
    settings = next(item for item in check.items if item.entry['kind'] == 'settings_fields')
    return check, settings, target, home


@pytest.mark.parametrize('choice', ['keep', 'overwrite'])
def test_summary_preserves_identity_partial_fields_unselected_agents_and_failures(tmp_path, choice):
    check, settings, target, home = summary_fixture(tmp_path)
    plan = plan_restore(check, state=home / 'state', process_names=(), conflict_choices={settings.entry['id']: choice})
    apply_restore(plan, processes=[])
    raw = tomllib.loads(target.read_text(encoding='utf-8'))
    assert raw['model'] == 'local-model'  # A conflict choice does not confirm security settings.
    assert raw['model_reasoning_effort'] == ('low' if choice == 'keep' else 'high')
    result = verify(check, restored=plan.restored, skipped=plan.skipped, conflicts=plan.conflicts)
    report = result.report()
    setting_check = next(v for v in report['checks'] if v.get('kind') == 'settings_fields')
    assert setting_check['status'] == ('KEPT' if choice == 'keep' else 'PARTIAL')
    assert set(setting_check['skipped_fields']) == ({'personality', 'model'} if choice == 'keep' else {'model'})
    assert ('personality' in raw) == (choice == 'overwrite')
    assert setting_check['retained_fields'] == (['model_reasoning_effort'] if choice == 'keep' else [])
    skills = next(g for g in report['groups'] if g['kind'] == 'skills_text')
    assert skills['counts'] == {'PASS': 4}
    unselected = next(g for g in report['groups'] if g['kind'] == 'not_selected')
    assert unselected['label'] == 'WorkBuddy AI' and len(unselected['check_indexes']) == 3
    assert sorted(i for g in report['groups'] for i in g['check_indexes']) == list(range(len(report['checks'])))
    assert result.questions and all(q['expected'].startswith('- Always explain') for q in result.questions)
    skill = next(v for v in check.items if v.entry['kind'] == 'skills_text')
    skill.target.write_bytes(b'corrupted skill')
    failed = verify(check, restored=plan.restored, skipped=plan.skipped, conflicts=plan.conflicts).report()
    assert failed['exit_code'] == 4
    assert next(g for g in failed['groups'] if g['kind'] == 'skills_text')['counts'] == {'FAIL': 1, 'PASS': 3}


def test_adding_missing_fields_to_existing_settings_also_requires_choice(tmp_path):
    check, settings, target, home = summary_fixture(tmp_path)
    original = b'[local_extension]\nx = 42\n'
    target.write_bytes(original)
    config = load_config(tmp_path / 'missing.json', home=home)
    check = preflight(tmp_path / 'summary.zip', home=home, config=config,
                      agents=frozenset({'codex'}), environ={}, processes=[])
    pending = plan_restore(check, state=home / 'state', process_names=(), conflict_choices={})
    assert pending.report()['pending_conflicts'] == 2
    assert all(v['reason'] == 'field_missing' for v in pending.conflicts)
    with pytest.raises(ValueError, match='choose overwrite or keep'):
        apply_restore(pending, processes=[])
    kept = plan_restore(check, state=home / 'state', process_names=(),
                        conflict_choices={settings.entry['id']: 'keep'})
    apply_restore(kept, processes=[])
    assert target.read_bytes() == original


@pytest.mark.parametrize('value', [True, [], {'entry': 'yes'}, {'': 'overwrite'}])
def test_desktop_rejects_invalid_choice_parameters(tmp_path, value):
    protocol = MachineProtocol(tmp_path / 'device.json', home=tmp_path, environ={})
    result = preview(protocol, 'machine_restore', bundle=str(tmp_path / 'missing.zip'), conflict_choices=value)
    assert result['error']['code'] == 'E_PARAMS_INVALID'
