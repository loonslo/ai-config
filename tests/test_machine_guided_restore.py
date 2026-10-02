from pathlib import Path
import subprocess

from _machine_fixtures import snapshot_tree,assert_tree_unchanged
from test_machine_preflight import fixture_bundle
from sync_core.machine.guide_restore import guide_restore,backup_files
from sync_core.machine.guided import GuideIO,forbidden_words
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore,apply_restore
from sync_core.machine.config import load_config
from sync_core.machine.paths import RootMap


SOFTWARE={'versions':{'python':'3.14.0'}}


def _io(answers):
    iterator=iter(answers);screen=[]
    return GuideIO(read=lambda prompt:next(iterator),write=screen.append),screen


def _run(bundle,home,config,mapper,ui,**kwargs):
    return guide_restore(bundle,io=ui,home=home,config=config,root_map=mapper,environ={},os_name='windows',
                         software=SOFTWARE,processes=kwargs.pop('processes',lambda:[]),**kwargs)


def _files(home):
    return {path.relative_to(home).as_posix():path.read_bytes() for name in ('.claude','.codex','.workbuddy','.workbuddy-ai','workspace')
            for path in (home/name).rglob('*') if path.is_file() and '.git' not in path.parts}


def test_all_enter_matches_equivalent_expert_and_cancel_zero_writes(tmp_path):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    before=snapshot_tree(home)
    ui,_=_io(['','','','','','q',''])
    assert _run(bundle,home,config,mapper,ui)==0
    assert_tree_unchanged(before,home)
    ui,screen=_io(['']*7)
    assert _run(bundle,home,config,mapper,ui)==0
    assert forbidden_words('\n'.join(ui.authored))==[]
    assert not any('--overwrite' in line for line in screen)
    other=tmp_path/'expert';other.mkdir()
    for name in ('.claude','.codex','.workbuddy','.workbuddy-ai'):(other/name).mkdir()
    other_project=other/'workspace/sample-project';other_project.mkdir(parents=True)
    subprocess.run(['git','init','-q',str(other_project)],check=True)
    rules=tuple((old,str(other/'workspace')) for old,_ in mapper.rules)
    other_config=load_config(tmp_path/'absent.json',home=other)
    check=preflight(bundle,home=other,config=other_config,root_map=RootMap(rules),environ={},processes=[])
    plan=plan_restore(check,state=other/'.ai-sync/state',process_names=other_config.running_process_names)
    apply_restore(plan,processes=[])
    # Memory directory encodes the native project, so compare those bytes separately.
    first=_files(home);second=_files(other)
    memory1={key: value for key,value in first.items() if '/projects/' in key}
    memory2={key: value for key,value in second.items() if '/projects/' in key}
    assert list(memory1.values())==list(memory2.values())
    assert {key:value for key,value in first.items() if '/projects/' not in key}=={key:value for key,value in second.items() if '/projects/' not in key}


def test_conflict_process_wait_and_undo_preserves_bytes(tmp_path):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    target=home/'.codex/AGENTS.md';target.write_bytes(b'local rules')
    ui,screen=_io(['','','','','','','',''])
    calls=iter([['Codex.exe'],[],[]])
    assert _run(bundle,home,config,mapper,ui,processes=lambda:next(calls))==0
    assert any('关闭正在运行' in line for line in screen)
    assert target.read_bytes()==b'local rules'
    assert target.with_name('AGENTS.md.from-bundle').exists()
    ui,_=_io(['','2','','',''])
    assert _run(bundle,home,config,mapper,ui)==0
    assert target.read_bytes()==b'local rules'
    assert not target.with_name('AGENTS.md.from-bundle').exists()


def test_displayed_trust_hash_change_refuses_and_bad_backup_is_actionable(tmp_path,monkeypatch):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    import sync_core.machine.guide_restore as module
    original=module.preflight
    captured=[]
    def capture(*args,**kwargs):
        result=original(*args,**kwargs);captured.append(result);return result
    monkeypatch.setattr(module,'preflight',capture)
    answers=iter(['','','','y',''])
    screen=[]
    def read(prompt):
        answer=next(answers)
        if answer=='y':
            captured[-1].trust_list[0]['path']+='-mutated'
        return answer
    ui=GuideIO(read=read,write=screen.append)
    assert _run(bundle,home,config,mapper,ui)==1
    assert not (home/'.codex/config.toml').exists()
    bad=tmp_path/'bad.zip';bad.write_bytes(b'not a ZIP')
    ui,screen=_io(['',''])
    assert _run(bad,home,config,mapper,ui)==1
    assert any('不是备份文件' in line for line in screen)


def test_discovery_is_top_level_and_dragged_file_works(tmp_path):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    nested=bundle.parent/'nested';nested.mkdir()
    (nested/'hidden.zip').write_bytes(bundle.read_bytes())
    (bundle.parent/'unrelated.zip').write_bytes(b'other')
    assert [item['path'] for item in backup_files([bundle.parent])]==[bundle]
    empty=tmp_path/'empty';empty.mkdir()
    ui,_=_io(['','"'+str(bundle)+'"','','','','','',''])
    assert _run(None,home,config,mapper,ui,desktop=lambda home:empty,drives=lambda:[],launcher=empty)==0
