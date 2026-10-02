import json
import subprocess
from pathlib import Path

import pytest

from _machine_fixtures import build_machine_home, snapshot_tree, assert_tree_unchanged
from sync_core.machine.backup import prepare_backup, apply_backup
from sync_core.machine.config import load_config
from sync_core.machine.paths import RootMap
from sync_core.machine.preflight import preflight, safe_destination


def fixture_bundle(tmp_path):
    source=build_machine_home(tmp_path/'source')
    config_file=tmp_path/'source-config.json'
    config_file.write_text(json.dumps({'core_projects':[str(source['project'])]}),encoding='utf-8')
    config=load_config(config_file,home=source['home'])
    out=tmp_path/'out';out.mkdir()
    plan=prepare_backup(home=source['home'],config=config,out=out,environ={},software={'versions':{'python':'3.14.0'}},git_keys=[])
    apply_backup(plan)
    target=tmp_path/'target';target.mkdir()
    for name in ('.claude','.codex','.workbuddy','.workbuddy-ai'):(target/name).mkdir()
    project=target/'workspace/sample-project';project.mkdir(parents=True)
    subprocess.run(['git','init','-q',str(project)],check=True)
    mapper=RootMap(((str(source['workspace']),str(target/'workspace')),),'windows','windows')
    target_config=load_config(tmp_path/'missing-config.json',home=target)
    return plan.writer.destination,target,project,target_config,mapper


def test_initialized_empty_target_new_conflicts_orphans_and_zero_writes(tmp_path):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    before=snapshot_tree(home)
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[],software={'versions':{'python':'4.0'}})
    assert all(item.status=='new' for item in check.items if item.entry['tier']==1)
    assert check.trust_list and check.software_warnings
    assert_tree_unchanged(before,home)
    (home/'.codex/AGENTS.md').write_text('local',encoding='utf-8')
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[])
    assert any(item.status=='differs' and item.target.name=='AGENTS.md' for item in check.items if item.target)
    from dataclasses import replace
    missing_mapper=RootMap(((str(Path(check.manifest['projects'][0]['source_path']).parent),str(home/'missing')),),'windows','windows')
    check=preflight(bundle,home=home,config=config,root_map=missing_mapper,environ={},processes=[])
    assert any(item.reason=='project_missing' for item in check.items)


def test_agent_filter_missing_roots_and_safe_paths(tmp_path):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    (home/'.codex').rmdir()
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},agents=frozenset({'codex'}),processes=['Codex.exe'])
    assert check.running==['Codex.exe']
    assert all(item.entry['agent']=='codex' and item.reason=='agent_not_initialized' for item in check.items)
    for relative in ('../auth.json','/outside','auth.json','skills/../../evil','skills/x:stream'):
        with pytest.raises(ValueError):safe_destination(home/'.codex',relative)


def test_windows_to_mac_project_and_memory_mapping(tmp_path):
    bundle,home,project,config,_=fixture_bundle(tmp_path)
    from sync_core.machine.bundle import read_bundle
    manifest,_=read_bundle(bundle)
    source_root=str(Path(manifest['projects'][0]['source_path']).parent)
    mapper=RootMap(((source_root,str(project.parent)),),'windows','darwin')
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},os_name='darwin',processes=[])
    memory=next(item for item in check.items if item.entry['agent']=='claude' and item.entry['kind']=='memory')
    from sync_core.machine.paths import derive_project_dir
    assert memory.target==home/'.claude/projects'/derive_project_dir(str(project))/'memory/MEMORY.md'
