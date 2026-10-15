import json

import pytest

from sync_core.machine.bundle import BundleError, BundleWriter, UnsupportedBundle, content_id, read_bundle, validate_bundle
from test_machine_bundle import _contents, _rewrite
from sync_core.machine.config import load_config
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore, apply_restore
from sync_core.machine.verify import verify
from sync_core.machine.undo import operations, undo


@pytest.mark.parametrize('version', [1, 2])
def test_versions_roundtrip_restore_verify_undo(tmp_path, version):
    source = tmp_path / 'source.zip'
    writer = BundleWriter(source, source={'os': 'windows'}, schema_version=version)
    writer.add_file('files/codex/main/AGENTS.md', b'original', agent='codex', instance='main', kind='rules', logical_path='codex:main/AGENTS.md')
    writer.finalize()
    home = tmp_path / 'home'
    (home / '.codex').mkdir(parents=True)
    target = home / '.codex/AGENTS.md'
    target.write_bytes(b'local')
    check = preflight(source, home=home, config=load_config(tmp_path / 'missing.json', home=home), environ={}, processes=[])
    plan = plan_restore(check, state=tmp_path / 'state', process_names=(), conflict_choices={check.items[0].entry['id']: 'overwrite'})
    apply_restore(plan, processes=[])
    assert target.read_bytes() == b'original'
    verification = verify(check, restored=plan.restored, skipped=plan.skipped, conflicts=plan.conflicts)
    assert any(c.get('entry_id') and c['status'] == 'PASS' for c in verification.checks)
    history = operations(tmp_path / 'state')
    undo(tmp_path / 'state', operation_id=history[0]['operation_id'], apply=True, process_names=(), processes=[])
    assert target.read_bytes() == b'local'
    assert validate_bundle(source)['schema_version'] == version


def _bundle(tmp_path):
    source = tmp_path / 'source.zip'
    writer = BundleWriter(source, source={'os': 'windows'})
    writer.add_file('files/codex/main/rules/default.rules', b'allow', agent='codex', instance='main', kind='approvals',
                    logical_path='codex:main/rules/default.rules', rule_id='CX-02', nature='A', group='approvals', conflict_group='rules')
    return source, writer.finalize()


@pytest.mark.parametrize(('field', 'value'), [('rule_id', 'x'*17), ('nature', 'Z'), ('group', 'unknown'), ('holder', 'unknown'),
                                           ('provenance_id', 1), ('conflict_group', 'x'*129), ('redactions', -1), ('redactions', True)])
def test_invalid_optional_metadata_is_rejected(tmp_path, field, value):
    source, manifest = _bundle(tmp_path)
    manifest['entries'][0][field] = value
    with pytest.raises(BundleError):
        validate_bundle(_rewrite(source, manifest, _contents(source)))


@pytest.mark.parametrize(('field','value'), [('agent','future-agent'), ('kind','future-kind')])
def test_unknown_types_return_specific_error(tmp_path, field, value):
    source, manifest = _bundle(tmp_path)
    manifest['entries'][0][field] = value
    with pytest.raises(UnsupportedBundle) as error:
        validate_bundle(_rewrite(source, manifest, _contents(source)))
    assert error.value.code == 'E7502'


def test_v1_rejects_v2_fields_and_content_identity_ignores_metadata(tmp_path):
    source, manifest = _bundle(tmp_path)
    before = content_id(manifest['entries'])
    manifest['entries'][0]['conflict_group'] = 'another'
    assert content_id(manifest['entries']) == before
    manifest['schema_version'] = 1
    with pytest.raises(BundleError):
        validate_bundle(_rewrite(source, manifest, _contents(source)))


def test_path_too_long_is_reported_and_does_not_fail_bundle(tmp_path):
    writer = BundleWriter(tmp_path / 'source.zip')
    added = writer.add_file('files/codex/main/skills/' + 'x'*240 + '/SKILL.md', b'x', agent='codex', instance='main', kind='skills', logical_path='codex:main/long')
    assert added is False and writer.oversize[0]['reason'] == 'path_too_long'
    writer.add_report('summary.md', 'safe')
    assert writer.finalize()['entries'][0]['kind'] == 'report'


def test_full_v1_all_legacy_kinds_restore_merge_repeat_and_undo(tmp_path):
    """Old metadata-free payloads must use every legacy restore path on the new engine."""
    import hashlib
    from test_machine_preflight import fixture_bundle
    from _machine_fixtures import snapshot_tree, assert_tree_unchanged
    from sync_core.machine.bundle import V1_AGENTS, V1_KINDS, V2_FIELDS
    modern, home, project, config, mapper = fixture_bundle(tmp_path)
    original, contents = read_bundle(modern)
    legacy = tmp_path/'legacy-v1.zip'
    writer = BundleWriter(legacy, source=original['source'], schema_version=1)
    for entry in original['entries']:
        if entry['agent'] == 'report':
            continue
        kind = entry['kind']
        data = contents[entry['archive_path']]
        if kind == 'skills':
            # v1 carried text skills; binary assets were not a legacy type.
            # Claude skills were reinstall-only in the old catalog.
            if entry['agent']=='claude' or b'\x00' in data or entry['archive_path'].endswith('.bin'):
                continue
            kind = 'skills_text'
        if kind not in V1_KINDS or entry['agent'] not in V1_AGENTS or entry['instance'] == 'desktop':
            continue
        writer.add_file(entry['archive_path'], data, agent=entry['agent'], instance=entry['instance'],
                        kind=kind, logical_path=entry['logical_path'], tier=entry['tier'], mode=entry['mode'],
                        restore=entry['restore'], project_id=entry['project_id'], flags=entry['flags'],
                        fields=entry.get('fields'), confirm_fields=entry.get('confirm_fields'))
    writer.add_report('summary.md', 'Legacy synthetic migration report.\n')
    manifest = writer.finalize(projects=original['projects'])
    assert {entry['kind'] for entry in manifest['entries']} == V1_KINDS
    assert {entry['agent'] for entry in manifest['entries']} == V1_AGENTS
    assert all(not V2_FIELDS.intersection(entry) for entry in manifest['entries'])
    bundle_hash = hashlib.sha256(legacy.read_bytes()).hexdigest()
    codex = home/'.codex/config.toml'
    codex.write_bytes(b'# original local file\nmodel_reasoning_effort = "low"\nlocal_option = "keep"\n')
    rule = home/'.codex/AGENTS.md'; rule.write_bytes(b'local rules before migration\n')
    before = snapshot_tree(home)
    check = preflight(legacy, home=home, config=config, root_map=mapper, environ={}, processes=[])
    assert check.manifest['schema_version'] == 1
    assert_tree_unchanged(before, home)
    assert all(item.reason in {'', 'manual_trust'} for item in check.items)
    options = dict(state=tmp_path/'legacy-state', process_names=(), confirm_security=True,
                   security_hash=check.security_list_hash, workbuddy_files=True, codex_trust=True,
                   confirm_trust=check.trust_list_hash)
    plan = plan_restore(check, **options,
                        conflict_choices={item.entry['id']:'overwrite' for item in check.items})
    assert_tree_unchanged(before, home)
    apply_restore(plan, processes=[])
    restored_files = [item for item in check.items if item.target and item.entry['mode']=='file']
    assert restored_files and {item.entry['agent'] for item in restored_files} == V1_AGENTS-{'report'}
    for item in restored_files:
        assert item.target.read_bytes() == contents[item.entry['archive_path']]
    import tomllib
    config_data = tomllib.loads(codex.read_text(encoding='utf-8'))
    assert config_data['local_option'] == 'keep' and config_data['model_reasoning_effort'] == 'high'
    assert config_data['projects'][str(project).replace('\\','/').lower()]['trust_level'] == 'trusted'
    result = verify(check, restored=plan.restored, skipped=plan.skipped, conflicts=plan.conflicts)
    assert not any(row['status']=='FAIL' for row in result.checks)
    assert all(any(row.get('entry_id')==item.entry['id'] and row['status']=='PASS' for row in result.checks)
               for item in restored_files)
    after = snapshot_tree(home)
    repeat_check = preflight(legacy, home=home, config=config, root_map=mapper, environ={}, processes=[])
    options.update(security_hash=repeat_check.security_list_hash, confirm_trust=repeat_check.trust_list_hash)
    repeat = plan_restore(repeat_check, **options)
    assert not repeat.changes
    apply_restore(repeat, processes=[])
    assert_tree_unchanged(after, home)
    history = operations(tmp_path/'legacy-state')
    assert len(history) == 1
    undo(tmp_path/'legacy-state', operation_id=history[0]['operation_id'], apply=True, process_names=(), processes=[])
    # Empty directories may remain; all original file bytes must be recovered.
    assert {p:v for p,v in snapshot_tree(home).items() if v[0]!='dir'} == {p:v for p,v in before.items() if v[0]!='dir'}
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() == bundle_hash
    assert not operations(tmp_path/'legacy-state')
