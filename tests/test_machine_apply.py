from pathlib import Path

import pytest

from test_machine_preflight import fixture_bundle
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore,apply_restore
from sync_core.transaction import write_file


def _plan(tmp_path):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[])
    plan=plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names)
    return bundle,home,project,config,mapper,plan


def test_empty_restore_identical_repeat_and_conflict_preservation(tmp_path):
    bundle,home,project,config,mapper,plan=_plan(tmp_path)
    report=apply_restore(plan,processes=[])
    assert report['backup'] and (home/'.codex/AGENTS.md').is_file()
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[])
    repeat=plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names)
    assert not repeat.changes
    target=home/'.codex/AGENTS.md'
    original=target.read_bytes()
    target.write_bytes(b'local rules')
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[])
    conflict=plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names)
    apply_restore(conflict,processes=[])
    assert target.read_bytes()==b'local rules'
    assert target.with_name('AGENTS.md.from-bundle').read_bytes()==original
    overwrite=plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names,overwrite=[target])
    # Rebuild after first conflict publication, which changed the alternate only.
    apply_restore(overwrite,processes=[])
    assert target.read_bytes()==original
    backup=Path(next((home/'.ai-sync/state/backups').iterdir()))
    assert (backup/'manifest.json').exists()


def test_process_refusal_target_edit_and_midway_failure_rollback(tmp_path):
    _,home,_,_,_,plan=_plan(tmp_path)
    with pytest.raises(ValueError,match='running'):apply_restore(plan,processes=['Codex.exe'])
    assert not (home/'.codex/AGENTS.md').exists()
    calls=[]
    def fail_second(path,data):
        if len(calls)==1:
            calls.append(path)
            raise OSError('injected failure')
        calls.append(path)
        write_file(path,data)
    with pytest.raises(OSError):apply_restore(plan,processes=[],writer=fail_second)
    assert all(not path.exists() for path in plan.changes)
    changed=next(iter(plan.changes))
    changed.parent.mkdir(parents=True,exist_ok=True)
    changed.write_bytes(b'new edit')
    with pytest.raises(ValueError,match='changed'):apply_restore(plan,processes=[])
    assert changed.read_bytes()==b'new edit'
