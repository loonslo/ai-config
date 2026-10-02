from _agent_homes import ReadTracker,SENTINEL
from test_machine_preflight import fixture_bundle
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore,apply_restore


def test_workbuddy_manual_only_preserves_protected_files_and_project_paths(tmp_path,monkeypatch):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    protected=[]
    for agent in ('workbuddy','workbuddy-ai'):
        root=home/f'.{agent}'
        for relative in ('keyblob','security/secret','app/connector-keys/key','state.db','settings.json'):
            path=root/relative
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(SENTINEL.encode())
            protected.append(path)
    tracker=ReadTracker(monkeypatch)
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[])
    default=plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names)
    assert all(default.changes.metadata['path_agents'][str(path)] not in {'workbuddy','workbuddy-ai'} for path in default.changes)
    explicit=plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names,workbuddy_files=True)
    apply_restore(explicit,processes=[])
    wb=[item for item in check.items if item.entry['agent'].startswith('workbuddy')]
    assert wb and all(item.target.read_bytes()==item.data for item in wb)
    assert (project/'.workbuddy/memory/note.md').is_file()
    assert (project/'.workbuddy-ai/memory/note.md').is_file()
    assert not list((home/'.workbuddy').rglob('AGENTS.md'))
    assert not list((home/'.workbuddy-ai').rglob('*_migration.json'))
    assert tracker.touched(protected)==[]
    assert all(path.read_bytes()==SENTINEL.encode() for path in protected)
