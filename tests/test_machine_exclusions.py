import json

from _agent_homes import ReadTracker,SENTINEL
from _machine_fixtures import build_machine_home,assert_no_sentinel
from sync_core.machine.backup import prepare_backup,apply_backup
from sync_core.machine.config import load_config,excluded_path
from sync_core.machine.guide_backup import filter_folders


def test_excluded_project_trees_and_custom_skill_never_opened(tmp_path,monkeypatch):
    source=build_machine_home(tmp_path/'source')
    home=source['home'];project=source['project']
    excluded=[]
    for branch in ('scratch-workspaces/demo','secret-notes'):
        for relative in ('.claude/settings.local.json','.workbuddy/memory/private.md','.workbuddy-ai/memory/private.md'):
            path=project/branch/relative
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(SENTINEL,encoding='utf-8')
            excluded.append(path)
    skill=home/'.codex/skills/diary/SKILL.md'
    skill.write_text(SENTINEL,encoding='utf-8');excluded.append(skill)
    path=tmp_path/'config.json'
    path.write_text(json.dumps({'core_projects':[str(project),str(home)],
                                'exclude_patterns':['**/scratch-workspaces/**','**/secret-notes/**','.codex/skills/diary/**']}),encoding='utf-8')
    config=load_config(path,home=home)
    output=tmp_path/'output';output.mkdir()
    tracker=ReadTracker(monkeypatch)
    plan=prepare_backup(home=home,config=config,out=output,environ={},software={'versions':{}},git_keys=[])
    assert len(plan.project_result.projects)==1
    assert not any('scratch-workspaces' in item['archive_path'] or 'secret-notes' in item['archive_path']
                   or item['archive_path'].startswith('files/codex/main/skills/diary') for item in plan.writer.entries)
    assert any(item['reason']=='excluded_by_config' for item in plan.exclusions)
    apply_backup(plan)
    assert_no_sentinel(plan.writer.destination)
    assert tracker.touched(excluded)==[]


def test_default_home_and_glob_root_excluded_from_folder_selection(tmp_path):
    home=tmp_path/'home';home.mkdir()
    config=load_config(tmp_path/'missing.json',home=home)
    root=home/'work/scratch-workspaces';root.mkdir(parents=True)
    assert excluded_path(home,config=config,home=home,os_name='windows')
    assert excluded_path(root,config=config,home=home,os_name='windows')
    assert filter_folders([str(home),str(root)],home=home,patterns=config.exclude_patterns,os_name='windows')==()
