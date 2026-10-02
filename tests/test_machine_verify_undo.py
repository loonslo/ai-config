import pytest

from test_machine_preflight import fixture_bundle
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore,apply_restore
from sync_core.machine.verify import verify
from sync_core.machine.undo import undo,operations


def test_full_restore_verify_corruption_and_undo_returns_file_state(tmp_path):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    target=home/'.codex/AGENTS.md';target.write_bytes(b'original local rules')
    state=home/'.ai-sync/state'
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[])
    plan=plan_restore(check,state=state,process_names=config.running_process_names,overwrite=[target],
                      confirm_security=True,workbuddy_files=True,codex_trust=True,confirm_trust=check.trust_list_hash)
    apply_restore(plan,processes=[])
    result=verify(check,restored=plan.restored,software={'versions':{'python':'3.14.0'}},reinstall_done=True)
    assert result.exit_code==0
    assert all(item['status']=='PASS' for item in result.checks if item.get('entry_id') and item.get('target'))
    assert result.questions
    target.write_bytes(b'corrupted')
    assert verify(check,restored=plan.restored).exit_code==4
    with pytest.raises(RuntimeError,match='修改'):
        undo(state,index=1,apply=True,process_names=config.running_process_names,processes=[])
    target.write_bytes(next(item.data for item in check.items if item.target==target))
    preview=undo(state,index=1)
    assert preview['mode']=='preview' and target.read_bytes()!=b'original local rules'
    undo(state,index=1,apply=True,process_names=config.running_process_names,processes=[])
    assert target.read_bytes()==b'original local rules'
    assert all(not path.exists() for path in plan.changes if path!=target)
    assert not operations(state)
    after=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[])
    assert [item.status for item in after.items]==[item.status for item in check.items]
