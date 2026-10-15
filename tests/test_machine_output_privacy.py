import json
from pathlib import Path
import subprocess

from sync_core.machine.privacy import secret_hits,redact,public_value
from sync_core.application.machine_protocol import MachineProtocol
from sync_core.machine.bundle import read_bundle
from sync_core.machine.paths import derive_project_dir
from _machine_fixtures import build_machine_home
from test_machine_desktop import preview,apply


def test_binary_secrets_are_detected_redacted_and_other_bytes_unchanged():
    sample=('sk-'+'A'*32).encode()
    data=b'\xff\x00header '+sample+b'\x00\xfeend'
    hits=secret_hits(data)
    assert len(hits)==1 and hits[0].kind=='token'
    clean,count=redact(data,hits)
    assert count==1 and clean==b'\xff\x00header <REDACTED>\x00\xfeend'
    assert not secret_hits(clean)
    assert public_value('D:\\tmp\\new-project\\rules.md')=='D:\\tmp\\new-project\\rules.md'
    assert public_value(r'person\u0040example.org')=='<邮箱已隐藏>'


def test_contact_path_opaque_selection_mapping_and_body_kept(tmp_path,monkeypatch):
    monkeypatch.setattr('sync_core.machine.procs.process_names',lambda:[])
    monkeypatch.setattr('sync_core.machine.backup.software_inventory',lambda **kwargs:{'versions':{}})
    monkeypatch.setattr('sync_core.machine.collect_login._git_credential_keys',lambda:[])
    email='person@example.org'
    paths=build_machine_home(tmp_path/email)
    (paths['home']/'.claude/CLAUDE.md').write_text('Contact '+email+'\nUse isolated fixtures when testing the project.\n',encoding='utf-8')
    (paths['home']/'.claude/settings.json').write_text(json.dumps({'model':email}),encoding='utf-8')
    registry=paths['home']/'.claude.json'
    registered=json.loads(registry.read_text(encoding='utf-8'))
    registered['projects'][str(paths['project'])]['mcpServers']={'remote':{'url':'https://example.org/mcp'}}
    registry.write_text(json.dumps(registered),encoding='utf-8')
    protocol=MachineProtocol(tmp_path/'device.json',home=paths['home'],environ={})
    detected=preview(protocol,'machine_detect')
    assert email not in json.dumps(detected) and detected['result']['projects'][0].startswith('folder:p-')
    out=tmp_path/'out';out.mkdir()
    backup=preview(protocol,'machine_backup',destination=str(out),agents=['claude','codex'],projects=detected['result']['projects'])
    assert backup['can_apply'],backup
    result=apply(protocol,backup)
    assert result['status']=='applied' and email not in json.dumps(result)
    bundle=Path(result['result']['destination']);manifest,files=read_bundle(bundle)
    assert email.encode() in files['files/claude/main/CLAUDE.md']
    source_project=manifest['projects'][0]
    target=tmp_path/'target';(target/'.claude').mkdir(parents=True);(target/'.codex').mkdir()
    project=tmp_path/'target-project'/email;project.mkdir(parents=True);subprocess.run(['git','init','-q',str(project)],check=True)
    target_protocol=MachineProtocol(tmp_path/'target-device.json',home=target,environ={})
    req={'bundle':str(bundle),'agents':['claude','codex'],'root_map':[{'from':'project:'+source_project['project_id'],'to':str(project)}],'confirm_security':True}
    restore=preview(target_protocol,'machine_restore',**req)
    assert restore['can_apply'],restore
    assert email not in json.dumps(restore)
    assert any(row['field']=='mcpServers.remote.url' and '<邮箱已隐藏>' in (row.get('project') or '') for row in restore['result']['security_list'])
    assert restore['result']['source_projects'][0]['mapping_source']=='project:'+source_project['project_id']
    applied=apply(target_protocol,restore)
    assert applied['status']=='applied' and email not in json.dumps(applied)
    assert email in (target/'.claude/CLAUDE.md').read_text()
    assert json.loads((target/'.claude/settings.json').read_text())['model']==email
    projects=json.loads((target/'.claude.json').read_text())['projects']
    migrated=next(value for path,value in projects.items() if path.replace('\\','/').casefold()==str(project).replace('\\','/').casefold())
    assert migrated['mcpServers']['remote']['url']=='https://example.org/mcp'
    encoded=derive_project_dir(str(project))
    assert (target/'.claude/projects'/encoded/'memory/MEMORY.md').exists()
    for path in Path(applied['result']['report_dir']).glob('*.md'):
        assert email not in path.read_text(encoding='utf-8')


def test_exception_messages_and_rule_questions_do_not_echo_credentials(tmp_path,monkeypatch):
    from sync_core.application.protocol import ProtocolError
    sample='sk-'+'A'*32
    protocol=MachineProtocol(tmp_path/'device.json',home=tmp_path,environ={})
    def fail(*args,**kwargs):raise ProtocolError('E_TEST','error for person@example.org '+sample)
    monkeypatch.setattr(protocol,'_invoke',fail)
    result=preview(protocol,'machine_detect')
    assert sample not in json.dumps(result) and 'person@example.org' not in json.dumps(result)


def test_privacy_guard_returns_actionable_safe_protocol_error(tmp_path, monkeypatch):
    monkeypatch.setattr('sync_core.machine.procs.process_names', lambda: [])
    sample = 'sk-' + 'A'*32
    monkeypatch.setattr('sync_core.machine.backup.software_inventory',
                        lambda **kwargs: {'versions': {'unknown': sample}})
    source = build_machine_home(tmp_path/'source')
    output = tmp_path/'output'; output.mkdir()
    protocol = MachineProtocol(tmp_path/'device.json', home=source['home'], environ={})
    result = preview(protocol, 'machine_backup', destination=str(output), agents=['codex'], projects=[])
    assert result['status'] == 'failed'
    assert result['error']['code'] == 'E_PRIVATE_CONTENT'
    message = result['error']['message']
    assert '生成报告' in message and '条目序号' in message
    assert '行号 1' in message and '识别类型 token' in message
    assert sample not in json.dumps(result) and str(source['home']) not in message
    assert list(output.iterdir()) == []


def test_metadata_error_does_not_echo_source_or_destination(tmp_path):
    from sync_core.machine.bundle import BundleWriter, PrivateContentError
    import pytest

    sample = 'sk-' + 'A'*32
    for writer in (BundleWriter(tmp_path/(sample+'.zip')),
                   BundleWriter(tmp_path/'safe.zip', source={'os': 'windows', 'home': sample})):
        with pytest.raises(PrivateContentError) as caught:
            writer.check_privacy(projects=[], exclusions=[], warnings=[])
        assert caught.value.code == 'E_PRIVATE_CONTENT'
        assert '元数据' in str(caught.value) and sample not in str(caught.value)


def test_ask_prefixed_skill_filename_survives_backup_and_restore(tmp_path):
    from sync_core.machine.backup import prepare_backup, apply_backup
    from sync_core.machine.config import load_config
    from sync_core.machine.preflight import preflight
    source = tmp_path/'source'
    skill = source/'.claude/skills/own'
    skill.mkdir(parents=True)
    (skill/'SKILL.md').write_text('Own skill.\n', encoding='utf-8')
    name = 'ask-' + 'questions-if-underspecified.md'
    (skill/name).write_text('Ask for missing requirements.\n', encoding='utf-8')
    output = tmp_path/'output'; output.mkdir()
    plan = prepare_backup(home=source, config=load_config(tmp_path/'missing.json',home=source),
                          out=output, agents=frozenset({'claude'}), environ={}, software={'versions':{}}, git_keys=[])
    assert any(e['archive_path'].endswith('/'+name) for e in plan.writer.entries)
    apply_backup(plan)
    target = tmp_path/'target'; (target/'.claude').mkdir(parents=True)
    check = preflight(plan.writer.destination,home=target,
                      config=load_config(tmp_path/'missing2.json',home=target),environ={},processes=[])
    assert any(item.target and item.target.name == name for item in check.items)
