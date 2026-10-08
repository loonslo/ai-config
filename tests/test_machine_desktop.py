"""Desktop previews and confirmations using synthetic assistant homes only."""
from pathlib import Path

import pytest

from sync_core.application.machine_protocol import MachineProtocol
from sync_core.machine.bundle import validate_bundle
from _machine_fixtures import build_machine_home, snapshot_tree, assert_tree_unchanged
from test_machine_preflight import fixture_bundle


def preview(protocol, operation, **params):
    return protocol.handle({'protocol_version': 1, 'request_id': 'test', 'type': 'preview',
                            'operation': operation, 'params': params})


def apply(protocol, plan):
    assert plan['status'] == 'preview', plan
    return protocol.handle({'protocol_version': 1, 'request_id': 'confirm', 'type': 'apply', 'plan_id': plan['plan_id']})


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    monkeypatch.setattr('sync_core.machine.procs.process_names', lambda: [])
    monkeypatch.setattr('sync_core.machine.backup.software_inventory', lambda **kwargs: {'versions': {'python': '3.14.0'}})
    monkeypatch.setattr('sync_core.machine.collect_login._git_credential_keys', lambda: [])


def test_backup_readonly_apply_and_changed_source_rejected(tmp_path):
    paths = build_machine_home(tmp_path / 'home')
    out = tmp_path / 'out'; out.mkdir()
    protocol = MachineProtocol(tmp_path / 'device.json', home=paths['home'], environ={})
    before = snapshot_tree(paths['home'])
    plan = preview(protocol, 'machine_backup', destination=str(out), agents=['codex'], projects=[str(paths['project'])])
    assert plan['can_apply'], plan
    assert not list(out.iterdir())
    assert_tree_unchanged(before, paths['home'])
    changed = paths['home'] / '.codex' / 'AGENTS.md'
    changed.write_text('Updated safe global rule for the desktop test.\n', encoding='utf-8')
    stale = apply(protocol, plan)
    assert stale['error']['code'] == 'E_PLAN_STALE', stale
    assert not list(out.iterdir())
    plan = preview(protocol, 'machine_backup', destination=str(out), agents=['codex'], projects=[str(paths['project'])])
    result = apply(protocol, plan)
    assert result['status'] == 'applied', result
    validate_bundle(Path(result['result']['destination']))
    assert apply(protocol, plan)['error']['code'] == 'E_PLAN_UNKNOWN'


def test_restore_conflicts_verification_history_and_undo(tmp_path):
    bundle, home, project, _, mapper = fixture_bundle(tmp_path)
    target = home / '.codex/AGENTS.md'; target.write_text('Keep local rules.\n', encoding='utf-8')
    before = snapshot_tree(home)
    protocol = MachineProtocol(tmp_path / 'device.json', home=home, environ={})
    params = {'bundle': str(bundle), 'agents': ['codex', 'claude'],
              'root_map': [{'from': old, 'to': new} for old, new in mapper.rules]}
    plan = preview(protocol, 'machine_restore', **params)
    assert plan['can_apply'], plan
    assert plan['result']['source_projects']
    assert_tree_unchanged(before, home)
    result = apply(protocol, plan)
    assert result['status'] == 'applied', result
    assert target.read_text() == 'Keep local rules.\n'
    assert target.with_name('AGENTS.md.from-bundle').exists()
    assert not any(v['status'] == 'FAIL' for v in result['result']['verification']['checks'])
    history = preview(protocol, 'machine_history')['result']['operations']
    assert len(history) == 1
    undo_plan = preview(protocol, 'machine_undo', operation_id=history[0]['operation_id'])
    result = apply(protocol, undo_plan)
    assert result['status'] == 'applied', result
    assert target.read_text() == 'Keep local rules.\n'
    assert not target.with_name('AGENTS.md.from-bundle').exists()
    assert not preview(protocol, 'machine_history')['result']['operations']


def test_changed_target_and_running_app_block_confirmation(tmp_path, monkeypatch):
    bundle, home, _, _, mapper = fixture_bundle(tmp_path)
    protocol = MachineProtocol(tmp_path / 'device.json', home=home, environ={})
    params = {'bundle': str(bundle), 'agents': ['codex'], 'root_map': [{'from': a, 'to': b} for a, b in mapper.rules]}
    plan = preview(protocol, 'machine_restore', **params)
    (home / '.codex/AGENTS.md').write_text('A local edit made after preview.\n', encoding='utf-8')
    assert apply(protocol, plan)['error']['code'] == 'E_PLAN_STALE'
    monkeypatch.setattr('sync_core.machine.procs.process_names', lambda: ['Codex.exe'])
    plan = preview(protocol, 'machine_restore', **params)
    assert not plan['can_apply']
    assert 'plan_id' not in plan


@pytest.mark.parametrize('operation,params', [('cloud', {}), ('package_import', {}), ('machine_backup', {'destination': 'relative'}),
                                              ('machine_restore', {'bundle': '/unused', 'agents': []})])
def test_desktop_rejects_old_actions_and_invalid_inputs(tmp_path, operation, params):
    protocol = MachineProtocol(tmp_path / 'device.json', home=tmp_path, environ={})
    assert preview(protocol, operation, **params)['status'] == 'failed'
