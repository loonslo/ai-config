import json

import pytest

from _machine_fixtures import build_machine_home, snapshot_tree, assert_tree_unchanged
from sync_core.machine.backup import prepare_backup, apply_backup
from sync_core.machine.bundle import BundleWriter, BundleError, read_bundle
from sync_core.machine.config import load_config
from sync_core.machine.preflight import preflight
from sync_core.machine.privacy import private_text


@pytest.mark.parametrize('value', [
    'person' + '@example.org',
    'https://' + 'reader:example' + '@example.org/path',
    'ssh://' + 'reader' + '@host/path',
    '{"note":"person\\u0040example.org"}',
])
def test_private_payloads_excluded_across_collectors(tmp_path, value):
    source = build_machine_home(tmp_path / 'source')
    home = source['home']
    paths = [home / '.claude/CLAUDE.md', home / '.codex/AGENTS.md',
             home / '.workbuddy/SOUL.md', home / '.workbuddy-ai/USER.md',
             source['project'] / '.claude/settings.local.json',
             home / '.codex/skills/diary/SKILL.md']
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'note': value}) if path.suffix == '.json' else value, encoding='utf-8')
    (home / '.claude/settings.json').write_text(json.dumps({'language': value}), encoding='utf-8')
    config_file = tmp_path / 'config.json'
    config_file.write_text(json.dumps({'core_projects': [str(source['project'])],
                                     'allow_secret_hit_paths': [str(paths[0])]}), encoding='utf-8')
    config = load_config(config_file, home=home)
    output = tmp_path / 'output'; output.mkdir()
    before = snapshot_tree(home)
    plan = prepare_backup(home=home, config=config, out=output, environ={},
                          software={'versions': {}}, git_keys=[])
    assert len([item for item in plan.exclusions if item['reason'] == 'secret_hit']) >= 6
    apply_backup(plan)
    manifest, files = read_bundle(plan.writer.destination)
    assert not private_text(json.dumps(manifest))
    assert all(not private_text(data) for data in files.values())
    assert_tree_unchanged(before, home)


def test_output_guard_rejects_private_report_metadata_and_late_changes(tmp_path):
    source = build_machine_home(tmp_path / 'source')
    home = source['home']; output = tmp_path / 'output'; output.mkdir()
    config = load_config(tmp_path / 'missing.json', home=home)
    kwargs = dict(home=home, config=config, out=output, environ={}, git_keys=[])
    with pytest.raises(BundleError, match='private content'):
        prepare_backup(**kwargs, software={'versions': {'unknown': 'person' + '@example.org'}})
    plan = prepare_backup(**kwargs, software={'versions': {}})
    plan.writer.source['home'] = 'person' + '@example.org'
    with pytest.raises(BundleError, match='private content'):
        plan.preview()
    with pytest.raises(BundleError, match='private content'):
        apply_backup(plan)
    assert list(output.iterdir()) == []


@pytest.mark.parametrize('location', ['payload', 'report', 'metadata'])
def test_old_bundle_private_content_rejected_before_target_reads(tmp_path, location, monkeypatch):
    from _agent_homes import ReadTracker
    private = 'person' + '@example.org'
    bundle = tmp_path / 'old.zip'
    writer = BundleWriter(bundle, source={'os': 'windows', 'home': private if location == 'metadata' else '/home'})
    writer.add_file('files/codex/main/AGENTS.md', (private if location == 'payload' else 'safe').encode(),
                    agent='codex', instance='main', kind='rules', logical_path='codex:main/AGENTS.md')
    writer.add_report('summary.md', private if location == 'report' else 'safe')
    writer.finalize()
    home = tmp_path / 'target'; (home / '.codex').mkdir(parents=True)
    target = home / '.codex/AGENTS.md'; target.write_text('local', encoding='utf-8')
    before = snapshot_tree(home)
    tracker = ReadTracker(monkeypatch)
    config = load_config(tmp_path / 'missing.json', home=home)
    with pytest.raises(BundleError, match='private content'):
        preflight(bundle, home=home, config=config, environ={}, processes=[])
    assert tracker.touched([target]) == []
    assert_tree_unchanged(before, home)
