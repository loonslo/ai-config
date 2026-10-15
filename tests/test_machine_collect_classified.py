from dataclasses import replace
import json
from pathlib import Path
import subprocess
import pytest

from _machine_fixtures import build_machine_home
from sync_core.machine.backup import prepare_backup, apply_backup
from sync_core.machine.config import load_config
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore, apply_restore
from sync_core.machine.paths import RootMap
from sync_core.machine.verify import verify


@pytest.mark.parametrize('git_state', ['tracked', 'ignored', 'untracked', 'tracked_ignored'])
def test_project_allowlist_ignores_git_state_and_never_queries_git(tmp_path, monkeypatch, git_state):
    from sync_core.machine.undo import undo
    from _agent_homes import ReadTracker

    home = tmp_path / 'home'
    target = tmp_path / 'target-home'
    project = tmp_path / '源 项目'
    mapped = tmp_path / '目标 项目'
    for folder in (home / '.claude', home / '.codex', target / '.claude', target / '.codex', project, mapped):
        folder.mkdir(parents=True)
    for folder in (project, mapped):
        subprocess.run(['git', 'init', '-q', str(folder)], check=True)
    payloads = {
        'AGENTS.md': b'local codex rule\n',
        'AGENTS.override.md': b'local codex override\n',
        'CLAUDE.md': b'local claude rule\n',
        'CLAUDE.local.md': b'local claude override\n',
        '.claude/commands/中文 command.md': b'project command\n',
        '.claude/agents/local.md': b'project agent\n',
        '.claude/output-styles/local.md': b'project style\n',
        '.claude/launch.json': b'{"version":"0.2.0"}\n',
        '.claude/local.md': b'project instruction\n',
        '.claude/skills/local/SKILL.md': b'local claude skill\n',
        '.claude/skills/local/data.bin': b'\x00\xfflocal asset',
        '.agents/skills/local/SKILL.md': b'local shared skill\n',
        '.codex/skills/local/SKILL.md': b'local codex skill\n',
        '.codex/config.toml': b'model_reasoning_effort="high"\n',
        '.codex/rules/default.rules': b'approved project command\n',
        '.codex/prompts/local.md': b'local project prompt\n',
        '.mcp.json': b'{"mcpServers":{"remote":{"url":"https://example.org/mcp"}}}\n',
        '.claude/settings.local.json': b'{"permissions":{"allow":["Read"]}}\n',
    }
    for name, data in payloads.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    ignored = git_state in {'ignored', 'tracked_ignored'}
    tracked = git_state in {'tracked', 'tracked_ignored'}
    if ignored:
        (project / '.gitignore').write_text('*\n', encoding='utf-8')
        result = subprocess.run(['git', '-C', str(project), 'check-ignore', '.claude/commands/中文 command.md'], capture_output=True)
        assert result.returncode == 0
    if tracked:
        subprocess.run(['git', '-C', str(project), 'add', '-f', '--', *payloads], check=True)
        # Local edits must be carried too, regardless of the index state.
        payloads['CLAUDE.md'] += b'local edit\n'
        (project / 'CLAUDE.md').write_bytes(payloads['CLAUDE.md'])
    git_files = [path for path in (project / '.git').rglob('*') if path.is_file()]
    metadata = {
        '.claude/skills/local/.git/config': b'forbidden repository remote',
        '.claude/skills/local/.git/HEAD': b'forbidden commit',
        '.claude/skills/local/.gitignore': b'forbidden ignore rules',
        '.claude/skills/local/.gitconfig': b'forbidden local config',
        '.claude/skills/local/.git-credentials': b'forbidden credential data',
        '.agents/skills/local/.git': b'gitdir: forbidden worktree metadata',
    }
    for name, data in metadata.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        git_files.append(path)
    tracker = ReadTracker(monkeypatch)
    import os
    original_scandir = os.scandir
    def no_git_directory(path):
        assert '.git' not in Path(path).parts, 'Git directory enumeration is forbidden'
        return original_scandir(path)
    monkeypatch.setattr(os, 'scandir', no_git_directory)
    original_run = subprocess.run
    def no_git(command, *args, **kwargs):
        assert Path(command[0]).name.casefold() not in {'git', 'git.exe'}, 'Git inspection is forbidden'
        return original_run(command, *args, **kwargs)
    monkeypatch.setattr(subprocess, 'run', no_git)
    config = replace(load_config(tmp_path / 'missing.json', home=home), core_projects=(project,))
    out = tmp_path / 'out'
    out.mkdir()
    backup = prepare_backup(home=home, config=config, out=out, agents=frozenset({'claude', 'codex'}),
                            environ={}, software={'versions': {}}, git_keys=[], user_environment={})
    project_entries = [entry for entry in backup.writer.entries if entry['project_id']]
    wanted = set(payloads)
    actual = {entry['logical_path'].split('/', 1)[1] for entry in project_entries}
    assert actual == wanted
    assert all('git_unavailable' not in entry['flags'] for entry in project_entries)
    assert {'PJ-01', 'PJ-03', 'PJ-04', 'PJ-05'} <= {entry.get('rule_id') for entry in project_entries}
    assert all('git_root' not in row and 'git_root_id' not in row for row in backup.project_result.projects)
    apply_backup(backup)
    check = preflight(backup.writer.destination, home=target, config=load_config(tmp_path / 'none.json', home=target),
                      root_map=RootMap(((str(project), str(mapped)),), 'windows', 'windows'), environ={}, processes=[])
    assert check.report()['needs_rebuild'] == 0
    assert '有程序文件未携带' not in check.todo()
    plan = plan_restore(check, state=tmp_path / 'state', process_names=(), confirm_security=True,
                        security_hash=check.security_list_hash)
    apply_restore(plan, processes=[])
    for name in payloads:
        path = mapped / name
        if name not in wanted:
            assert not path.exists()
        elif name == '.mcp.json':
            assert json.loads(path.read_text()) == json.loads(payloads[name])
        else:
            assert path.read_bytes() == payloads[name]
    assert not any((mapped / name).exists() for name in metadata)
    assert verify(check, restored=plan.restored, skipped=plan.skipped, conflicts=plan.conflicts).exit_code == 0
    undo(tmp_path / 'state', index=1, apply=True, process_names=(), processes=[])
    for folder, directories, files in os.walk(mapped):
        directories[:] = [name for name in directories if name != '.git']
        assert not files
    for name, data in payloads.items():
        assert (project / name).read_bytes() == data
    assert tracker.touched(git_files) == []
    assert all('/.git/' not in entry['archive_path'] for entry in backup.writer.entries)


def test_new_rules_scripts_fields_and_projects_roundtrip(tmp_path):
    paths = build_machine_home(tmp_path/'source')
    home, project = paths['home'], paths['project']
    extra = {
        home/'.claude/commands/example.md': b'command content',
        home/'.claude/agents/example.md': b'agent content',
        home/'.claude/output-styles/example.md': b'style content',
        home/'.claude/keybindings.json': b'{"bindings":{}}',
        home/'.claude/plans/example.md': b'plan content',
        home/'.codex/rules/default.rules': b'approved command rule',
        home/'.codex/prompts/example.md': b'prompt content',
        home/'.codex/memories/example.md': b'new memory',
        home/'.workbuddy-ai/scripts/example.py': b'print(1)',
        project/'AGENTS.override.md': b'local untracked rule',
        project/'.claude/local.md': b'local instruction',
        project/'.claude/commands/example.md': b'project command',
        project/'.claude/skills/example/SKILL.md': b'project skill',
        project/'.claude/skills/example/data.bin': b'\x00\xff',
        project/'.agents/skills/shared/SKILL.md': b'project shared skill',
        project/'.codex/rules/default.rules': b'project approval',
        project/'.codex/prompts/one.md': b'project prompt',
        project/'.codex/config.toml': b'model_reasoning_effort = "high"\n',
    }
    for path, data in extra.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    tracked = project/'CLAUDE.md'
    tracked.write_bytes(b'Git carries this')
    subprocess.run(['git','-C',str(project),'add','CLAUDE.md'],check=True)
    (home/'.claude/settings.json').write_text(json.dumps({'language':'zh', 'env':{'AI_BASE_URL':'https://example.org', 'API_TOKEN':'not-exported'}, 'hooks':{'onStart':[{'command':'echo hello'}]}}),encoding='utf-8')
    (home/'.codex/config.toml').write_text('[shell_environment_policy.set]\nAI_BASE_URL="https://example.org"\nAPI_TOKEN="not-exported"\n[mcp_servers.remote]\nurl="https://example.org/mcp"\n',encoding='utf-8')
    (project/'.mcp.json').write_text(json.dumps({'mcpServers':{'remote':{'url':'https://example.org/mcp','env':{'API_TOKEN':'not-exported','AI_OPTION':'yes'}}}}),encoding='utf-8')
    desktop = home/'AppData/Roaming/Claude'
    desktop.mkdir(parents=True)
    (desktop/'claude_desktop_config.json').write_text(json.dumps({'mcpServers':{'remote':{'url':'https://example.org/mcp'}},'preferences':{'locale':'zh','deviceId':'not-exported'}}),encoding='utf-8')
    config = replace(load_config(tmp_path/'missing.json',home=home), core_projects=(project,))
    out = tmp_path/'out';out.mkdir()
    backup = prepare_backup(home=home,config=config,out=out,environ={},software={'versions':{}},git_keys=[])
    assert all(b'not-exported' not in b for b in backup.writer._files.values())
    assert any(e['archive_path'].endswith('/claude/CLAUDE.md') for e in backup.writer.entries)
    apply_backup(backup)
    target_home = tmp_path/'target'
    for name in ('.claude','.codex','.workbuddy','.workbuddy-ai','AppData/Roaming/Claude'):
        (target_home/name).mkdir(parents=True)
    target_project = tmp_path/'target-project'; target_project.mkdir()
    subprocess.run(['git','init','-q',str(target_project)],check=True)
    config = load_config(tmp_path/'missing2.json',home=target_home)
    mapper = RootMap(((str(project),str(target_project)),), 'windows','windows')
    check = preflight(backup.writer.destination,home=target_home,config=config,root_map=mapper,environ={},processes=[])
    plan = plan_restore(check,state=tmp_path/'state',process_names=(),workbuddy_files=True,confirm_security=True,
                        security_hash=check.security_list_hash)
    apply_restore(plan,processes=[])
    for source, data in extra.items():
        target = target_project/source.relative_to(project) if source.is_relative_to(project) else target_home/source.relative_to(home)
        assert target.read_bytes() == data, str(source)
    assert json.loads((target_home/'.claude/settings.json').read_text())['env'] == {'AI_BASE_URL':'https://example.org'}
    assert json.loads((target_project/'.mcp.json').read_text())['mcpServers']['remote']['env'] == {'AI_OPTION':'yes'}
    verification = verify(check,restored=plan.restored,skipped=plan.skipped,conflicts=plan.conflicts)
    assert verification.exit_code == 0


def test_registered_project_mcp_maps_dotted_paths_and_preserves_local_fields(tmp_path):
    home = tmp_path/'source'; (home/'.claude').mkdir(parents=True)
    project = home/'workspace/project.with.dot'; project.mkdir(parents=True)
    other = home/'workspace/other'; other.mkdir()
    server = {'url':'https://example.org/mcp', 'env':{'AI_OPTION':'yes','API_TOKEN':'not-exported'},
              'deviceId':'not-exported', 'unknown':'not-exported'}
    (home/'.claude.json').write_text(json.dumps({'projects':{
        str(project):{'mcpServers':{'remote':server},'hasTrustDialogAccepted':True},
        str(other):{'mcpServers':{'unselected':server}}}}),encoding='utf-8')
    config = replace(load_config(tmp_path/'missing.json',home=home), core_projects=(project,))
    out = tmp_path/'out'; out.mkdir()
    backup = prepare_backup(home=home,config=config,out=out,agents=frozenset({'claude'}),environ={},software={'versions':{}},git_keys=[])
    entries = [e for e in backup.writer.entries if e['kind']=='settings_fields' and e['project_id']]
    assert len(entries)==1 and entries[0]['rule_id']=='CC-14'
    assert b'not-exported' not in backup.writer._files[entries[0]['archive_path']]
    assert b'unselected' not in backup.writer._files[entries[0]['archive_path']]
    apply_backup(backup)
    target = tmp_path/'target'; (target/'.claude').mkdir(parents=True)
    mapped = target/'workspace/new.project'; mapped.mkdir(parents=True)
    key = str(mapped).replace('\\','/').upper()
    registry = target/'.claude.json'
    original = {'oauthAccount':'keep-local', 'projects':{key:{'hasTrustDialogAccepted':False, 'local':'keep',
                'mcpServers':{'remote':{'url':'https://local.example/mcp'},'local':{'command':'local'}}},
                'untouched':{'local':'keep'}}}
    original_bytes = json.dumps(original).encode(); registry.write_bytes(original_bytes)
    check = preflight(backup.writer.destination,home=target,config=load_config(tmp_path/'none.json',home=target),
                      root_map=RootMap(((str(project),str(mapped)),),'windows','windows'),environ={},processes=[])
    item = next(i for i in check.items if i.entry['id']==entries[0]['id'])
    assert item.target==registry and item.field_status['mcpServers.remote.url']=='differs'
    assert registry.read_bytes()==original_bytes
    denied = plan_restore(check,state=tmp_path/'not-confirmed',process_names=())
    assert not denied.changes
    plan = plan_restore(check,state=tmp_path/'state',process_names=(),confirm_security=True,
                        security_hash=check.security_list_hash, conflict_choices={item.entry['id']:'overwrite'})
    apply_restore(plan,processes=[])
    actual = json.loads(registry.read_bytes())
    assert set(actual['projects'])=={key,'untouched'}
    assert actual['projects'][key]['mcpServers']['remote']=={'url':'https://example.org/mcp','env':{'AI_OPTION':'yes'}}
    assert actual['projects'][key]['mcpServers']['local']=={'command':'local'}
    assert actual['projects'][key]['local']=='keep' and actual['projects'][key]['hasTrustDialogAccepted'] is False
    assert actual['oauthAccount']=='keep-local' and actual['projects']['untouched']==original['projects']['untouched']
    result = verify(check,restored=plan.restored,skipped=plan.skipped,conflicts=plan.conflicts)
    assert next(r for r in result.checks if r.get('entry_id')==item.entry['id'])['status']=='PASS'
    from sync_core.machine.undo import undo, operations
    undo(tmp_path/'state',operation_id=operations(tmp_path/'state')[0]['operation_id'],apply=True,process_names=(),processes=[])
    assert registry.read_bytes()==original_bytes


@pytest.mark.parametrize('source_name',['.mcp.json','.claude.json','claude_desktop_config.json','settings.json'])
@pytest.mark.parametrize('leaf',['deviceId','unknown','url.extra','headers.authorization','env.API_TOKEN'])
def test_mcp_subtrees_do_not_broaden_leaf_whitelist(source_name, leaf):
    from sync_core.machine.preflight import allowed_fields
    from sync_core.machine.bundle import BundleError
    value = 'safe-but-not-approved'
    nested = value
    for name in reversed(leaf.split('.')):
        nested = {name:nested}
    payload = json.dumps({'fields':{'mcpServers':{'remote':nested}}}).encode()
    with pytest.raises(BundleError):
        allowed_fields('claude',payload,target_os='windows',source_name=source_name)


@pytest.mark.parametrize('failure',['missing_git','not_git_repository'])
def test_git_availability_does_not_affect_allowlisted_project_files(tmp_path, monkeypatch, failure):
    home = tmp_path/'home'; (home/'.codex').mkdir(parents=True)
    project = home/'workspace/project'; project.mkdir(parents=True)
    originals = {'AGENTS.override.md':b'non-git rule\n', '.codex/prompts/one.md':b'non-git prompt\n',
                 '.agents/skills/own/SKILL.md':b'non-git skill\n'}
    for relative,data in originals.items():
        path = project/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
    if failure=='missing_git':
        def no_git(*args,**kwargs):
            raise FileNotFoundError('synthetic missing git')
        monkeypatch.setattr(subprocess,'run',no_git)
    else:
        # tmp_path is under the repository; isolate the intended non-repository result.
        def not_repository(command, **kwargs):
            if kwargs.get('check'):
                raise subprocess.CalledProcessError(128,command)
            return subprocess.CompletedProcess(command,128,stdout=b'',stderr=b'')
        monkeypatch.setattr(subprocess,'run',not_repository)
    config=replace(load_config(tmp_path/'none.json',home=home),core_projects=(project,))
    out=tmp_path/'out'; out.mkdir()
    backup=prepare_backup(home=home,config=config,out=out,agents=frozenset({'codex'}),environ={},software={'versions':{}},git_keys=[])
    carried=[entry for entry in backup.writer.entries if entry['project_id'] and entry['mode']=='file']
    assert len(carried)==3 and all('git_unavailable' not in entry['flags'] for entry in carried)
    apply_backup(backup)
    target=tmp_path/'target'; (target/'.codex').mkdir(parents=True)
    mapped=target/'workspace/project'; mapped.mkdir(parents=True)
    check=preflight(backup.writer.destination,home=target,config=load_config(tmp_path/'none2.json',home=target),
                    root_map=RootMap(((str(project),str(mapped)),),'windows','windows'),environ={},processes=[])
    plan=plan_restore(check,state=tmp_path/'state',process_names=())
    apply_restore(plan,processes=[])
    assert {(mapped/p).read_bytes() for p in originals}==set(originals.values())
    for relative,data in originals.items():
        assert (mapped/relative).read_bytes()==data
    result=verify(check,restored=plan.restored,skipped=plan.skipped,conflicts=plan.conflicts)
    assert result.exit_code==0


@pytest.mark.parametrize('keep_second',[False,True])
def test_global_and_two_project_mcp_share_one_write_and_undo(tmp_path, keep_second):
    from sync_core.machine.undo import operations, undo
    home=tmp_path/'source'; (home/'.claude').mkdir(parents=True)
    source_projects=[home/'workspace/first.project',home/'workspace/second.project']
    for path in source_projects: path.mkdir(parents=True)
    server=lambda url: {'mcpServers':{'remote':{'url':url}}}
    source_data={**server('https://global.example/mcp'), 'projects':{
        str(path):server(f'https://project{i}.example/mcp') for i,path in enumerate(source_projects)}}
    (home/'.claude.json').write_text(json.dumps(source_data),encoding='utf-8')
    config=replace(load_config(tmp_path/'none.json',home=home),core_projects=tuple(source_projects))
    out=tmp_path/'out';out.mkdir()
    backup=prepare_backup(home=home,config=config,out=out,agents=frozenset({'claude'}),environ={},software={'versions':{}},git_keys=[])
    apply_backup(backup)
    target=tmp_path/'target';(target/'.claude').mkdir(parents=True)
    projects=[target/'workspace/first.new',target/'workspace/second.new']
    for path in projects:path.mkdir(parents=True)
    keys=[str(p).replace('\\','/').upper() for p in projects]
    registry=target/'.claude.json'
    before={**server('https://local.example/mcp'),'local':'keep','projects':{
        keys[0]:{**server('https://local-first.example/mcp'),'local':'first','hasTrustDialogAccepted':False},
        keys[1]:{'local':'second'},'untouched':{'local':'third'}}}
    before_bytes=json.dumps(before).encode();registry.write_bytes(before_bytes)
    check=preflight(backup.writer.destination,home=target,config=load_config(tmp_path/'none2.json',home=target),
                    root_map=RootMap(tuple((str(a),str(b)) for a,b in zip(source_projects,projects)),'windows','windows'),environ={},processes=[])
    items=[i for i in check.items if i.entry['kind']=='settings_fields']
    assert len(items)==3 and all(i.target==registry for i in items)
    assert {row['project'].casefold() if row.get('project') else None for row in check.security_list}=={None,*[str(p).casefold() for p in projects]}
    choices={i.entry['id']:'keep' if keep_second and i.field_path==('projects',keys[1]) else 'overwrite' for i in items}
    plan=plan_restore(check,state=tmp_path/'state',process_names=(),confirm_security=True,
                      security_hash=check.security_list_hash,conflict_choices=choices)
    assert len(plan.changes)==1 and registry.read_bytes()==before_bytes
    apply_restore(plan,processes=[])
    actual=json.loads(registry.read_bytes())
    assert actual['mcpServers']['remote']['url']=='https://global.example/mcp'
    assert actual['projects'][keys[0]]['mcpServers']['remote']['url']=='https://project0.example/mcp'
    assert actual['projects'][keys[0]]['local']=='first' and actual['projects'][keys[0]]['hasTrustDialogAccepted'] is False
    assert actual['projects'][keys[1]]==before['projects'][keys[1]] if keep_second else actual['projects'][keys[1]]=={
        'local':'second',**server('https://project1.example/mcp')}
    assert actual['projects']['untouched']==before['projects']['untouched'] and actual['local']=='keep'
    result=verify(check,restored=plan.restored,skipped=plan.skipped,conflicts=plan.conflicts)
    assert not any(row['status']=='FAIL' for row in result.checks)
    statuses={row['entry_id']:row['status'] for row in result.checks if row.get('entry_id')}
    assert all(statuses[i.entry['id']]==('KEPT' if choices[i.entry['id']]=='keep' else 'PASS') for i in items)
    history=operations(tmp_path/'state');assert len(history)==1 and len(history[0]['changes'])==1
    undo(tmp_path/'state',operation_id=history[0]['operation_id'],apply=True,process_names=(),processes=[])
    assert registry.read_bytes()==before_bytes


@pytest.mark.parametrize('mode',['different','identical','keep_second','disjoint'])
def test_two_source_projects_same_destination_do_not_silently_replace_fields(tmp_path, monkeypatch, mode):
    from sync_core.machine.bundle import BundleError
    home=tmp_path/'source';(home/'.claude').mkdir(parents=True)
    sources=[home/'workspace/one',home/'workspace/two']
    for path in sources:path.mkdir(parents=True)
    services=[{'remote':{'url':'https://first.example/mcp'}},
              {'other' if mode=='disjoint' else 'remote':{'url':'https://first.example/mcp' if mode=='identical' else 'https://second.example/mcp'}}]
    (home/'.claude.json').write_text(json.dumps({'projects':{str(p):{'mcpServers':s} for p,s in zip(sources,services)}}),encoding='utf-8')
    config=replace(load_config(tmp_path/'none.json',home=home),core_projects=tuple(sources))
    out=tmp_path/'out';out.mkdir()
    backup=prepare_backup(home=home,config=config,out=out,agents=frozenset({'claude'}),environ={},software={'versions':{}},git_keys=[])
    apply_backup(backup)
    target=tmp_path/'target';(target/'.claude').mkdir(parents=True)
    project=target/'workspace/joined';project.mkdir(parents=True)
    registry=target/'.claude.json';before=b'{"local":"keep","projects":{}}\n';registry.write_bytes(before)
    check=preflight(backup.writer.destination,home=target,config=load_config(tmp_path/'none2.json',home=target),
                    root_map=RootMap(tuple((str(p),str(project)) for p in sources),'windows','windows'),environ={},processes=[])
    items=[i for i in check.items if i.entry['kind']=='settings_fields'];assert len(items)==2
    options=dict(state=tmp_path/'state',process_names=(),confirm_security=True,security_hash=check.security_list_hash,
                 conflict_choices={i.entry['id']:'keep' if mode=='keep_second' and i==items[1] else 'overwrite' for i in items})
    if mode=='different':
        with pytest.raises(BundleError,match='多个来源设置'):
            plan_restore(check,**options)
        assert registry.read_bytes()==before and not (tmp_path/'state').exists()
        from sync_core.application.machine_protocol import MachineProtocol
        from test_machine_desktop import preview,apply
        monkeypatch.setattr('sync_core.machine.procs.process_names',lambda:[])
        protocol=MachineProtocol(tmp_path/'device.json',home=target,environ={})
        params={'bundle':str(backup.writer.destination),'agents':['claude'],'confirm_security':True,
                'root_map':[{'from':str(p),'to':str(project)} for p in sources],
                'conflict_choices':{i.entry['id']:'overwrite' for i in items}}
        failed=preview(protocol,'machine_restore',**params)
        assert failed['status']=='failed' and 'plan_id' not in failed
        assert '多个来源设置' in failed['error']['message'] and registry.read_bytes()==before
        params['conflict_choices']={i.entry['id']:'overwrite' if i==items[0] else 'keep' for i in items}
        resolved=preview(protocol,'machine_restore',**params)
        assert resolved['can_apply'],resolved
        applied=apply(protocol,resolved)
        assert applied['status']=='applied',applied
        table=next(iter(json.loads(registry.read_bytes())['projects'].values()))['mcpServers']
        assert table==services[0]
        assert not any(row['status']=='FAIL' for row in applied['result']['verification']['checks'])
        return
    plan=plan_restore(check,**options);assert len(plan.changes)==1
    apply_restore(plan,processes=[])
    result=verify(check,restored=plan.restored,skipped=plan.skipped,conflicts=plan.conflicts)
    assert not any(row['status']=='FAIL' for row in result.checks)
    table=next(iter(json.loads(registry.read_bytes())['projects'].values()))['mcpServers']
    assert table=={**services[0],**services[1]} if mode!='keep_second' else table==services[0]
    from sync_core.machine.undo import operations,undo
    undo(tmp_path/'state',operation_id=operations(tmp_path/'state')[0]['operation_id'],apply=True,process_names=(),processes=[])
    assert registry.read_bytes()==before
