from test_machine_preflight import fixture_bundle
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore,apply_restore
from sync_core.machine.paths import derive_project_dir,git_root


def test_memory_reuses_case_variant_and_preserves_index_conflict(tmp_path):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    encoded=derive_project_dir(str(git_root(project)))
    existing=home/'.claude/projects'/encoded.swapcase()/'memory'
    existing.mkdir(parents=True)
    index=existing/'MEMORY.md'
    index.write_bytes(b'local memory index')
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[])
    memory=next(item for item in check.items if item.entry['kind']=='memory' and item.entry['agent']=='claude')
    assert memory.target==index
    plan=plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names)
    apply_restore(plan,processes=[])
    assert index.read_bytes()==b'local memory index'
    assert index.with_name('MEMORY.md.from-bundle').read_bytes()==memory.data
    assert len(list((home/'.claude/projects').iterdir()))==1
    assert any('记忆索引' in warning for warning in plan.warnings)


def test_memory_empty_target_and_mac_mapping_raw_bytes(tmp_path):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    from sync_core.machine.paths import RootMap
    mapper=RootMap(mapper.rules,'windows','darwin')
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[],os_name='darwin')
    plan=plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names)
    apply_restore(plan,processes=[])
    memory=next(item for item in check.items if item.entry['kind']=='memory' and item.entry['agent']=='claude')
    assert memory.target.read_bytes()==memory.data
    assert memory.target.parent.parent.name==derive_project_dir(str(git_root(project)))
