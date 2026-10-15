"""History tests use synthetic roots, small limits, and no real assistant data."""
import hashlib
import errno
import json
from pathlib import Path
import zipfile

import pytest

from sync_core.machine.history import HistoryLimits, HistoryError, prepare_history, write_history, validate_history
from _agent_homes import ReadTracker


PARENT = hashlib.sha256(b'main bundle').hexdigest()


def _source(tmp_path):
    root = tmp_path/'home/.codex'
    file = root/'sessions/2026/10/test.jsonl'
    file.parent.mkdir(parents=True,exist_ok=True)
    file.write_bytes((json.dumps({'message':'中文 ' + 'x'*30}, ensure_ascii=False)+'\n').encode()*14)
    return root, file


def _paths(tmp_path, plan):
    return [tmp_path/f'history-{i+1}.zip' for i in range(len(plan.entries))]


def test_unselected_history_does_not_enumerate_or_read(tmp_path, monkeypatch):
    root, file = _source(tmp_path)
    tracker = ReadTracker(monkeypatch)
    import sync_core.machine.history as module
    monkeypatch.setattr(module.os, 'walk', lambda *a, **k: pytest.fail('unselected traversal'))
    plan = prepare_history({'codex':root}, selected=False)
    assert not plan.sources and not plan.entries and not tracker.touched([file])


def test_one_large_source_splits_streams_and_roundtrips_bytes(tmp_path):
    root, file = _source(tmp_path)
    limits = HistoryLimits(part_bytes=130, chunk_bytes=60, members=2)
    plan = prepare_history({'codex':root}, selected=True, limits=limits)
    assert len(plan.entries)>2 and plan.report()['bytes']==file.stat().st_size
    assert not list(tmp_path.glob('*.zip'))
    paths = _paths(tmp_path, plan)
    refs = write_history(plan, paths, parent_content_id=PARENT)
    assert len(refs)==len(paths)
    manifests = validate_history(paths,parent_content_id=PARENT,limits=limits)
    restored = bytearray()
    for path, manifest in zip(paths,manifests):
        with zipfile.ZipFile(path) as archive:
            assert archive.namelist()[-1]=='manifest.json'
            for entry in manifest['entries']:
                assert entry['size']<=60
                restored.extend(archive.read(entry['archive_path']))
    assert bytes(restored)==file.read_bytes() and not list(tmp_path.glob('*.partial'))
    assert not validate_history([],parent_content_id=PARENT)


def test_history_privacy_and_skip_are_whole_file(tmp_path):
    root, file = _source(tmp_path)
    token = 'sk-'+'a'*30
    file.write_bytes((json.dumps({'message':token,'email':'writer@example.test'})+'\n').encode())
    plan = prepare_history({'codex':root},selected=True)
    assert plan.report()['redactions']==1 and len(plan.sources)==1
    paths=_paths(tmp_path,plan); write_history(plan,paths,parent_content_id=PARENT)
    with zipfile.ZipFile(paths[0]) as archive:
        body=archive.read(plan.entries[0][0]['archive_path'])
        assert token.encode() not in body and b'writer@example.test' in body
        assert json.loads(body)['message']=='<REDACTED>'
    skipped=prepare_history({'codex':root},selected=True,policy='skip')
    assert not skipped.entries and skipped.exclusions[0]['reason']=='secret_file_skipped'
    assert token.encode() in file.read_bytes()


@pytest.mark.parametrize('body,reason',[(b'{broken}\n','invalid_jsonl'),(b'\xff\n','invalid_jsonl'),(b'x'*81,'line_too_long')])
def test_invalid_or_oversized_lines_are_explicit_exclusions(tmp_path,body,reason):
    root,file=_source(tmp_path);file.write_bytes(body)
    plan=prepare_history({'codex':root},selected=True,limits=HistoryLimits(line_bytes=80))
    assert not plan.entries and plan.exclusions[0]['reason']==reason


def test_changed_sources_and_existing_parts_block_publication(tmp_path):
    root,file=_source(tmp_path)
    plan=prepare_history({'codex':root},selected=True,limits=HistoryLimits(part_bytes=100,chunk_bytes=50))
    paths=_paths(tmp_path,plan)
    file.write_bytes(b'{"new":"different"}\n')
    with pytest.raises(HistoryError):write_history(plan,paths,parent_content_id=PARENT)
    assert not list(tmp_path.glob('*.zip')) and not list(tmp_path.glob('*.partial'))
    plan=prepare_history({'codex':root},selected=True)
    paths=_paths(tmp_path,plan);paths[0].write_bytes(b'existing')
    with pytest.raises(HistoryError):write_history(plan,paths,parent_content_id=PARENT)
    assert paths[0].read_bytes()==b'existing' and not list(tmp_path.glob('*.partial'))


def test_missing_swapped_and_wrong_parent_parts_are_rejected(tmp_path):
    root,file=_source(tmp_path)
    plan=prepare_history({'codex':root},selected=True,limits=HistoryLimits(part_bytes=140,chunk_bytes=70))
    paths=_paths(tmp_path,plan);write_history(plan,paths,parent_content_id=PARENT)
    for members,parent in [(paths[:-1],PARENT),(list(reversed(paths)),PARENT),(paths,'0'*64)]:
        with pytest.raises(HistoryError):validate_history(members,parent_content_id=parent,limits=plan.limits)


def test_allowlisted_history_only_and_budget_failure(tmp_path,monkeypatch):
    root,file=_source(tmp_path)
    denied=root/'sessions/auth.json';denied.write_bytes(b'not read')
    db=root/'state.sqlite';db.write_bytes(b'not read')
    tracker=ReadTracker(monkeypatch)
    with pytest.raises(HistoryError):prepare_history({'codex':root},selected=True,limits=HistoryLimits(total_bytes=40,chunk_bytes=20))
    assert not tracker.touched([denied,db])
    claude=tmp_path/'home/.claude';(claude/'projects/encoded').mkdir(parents=True)
    (claude/'projects/encoded/chat.jsonl').write_bytes(b'{"text":"hi"}\n')
    (claude/'projects/encoded/nested').mkdir()
    nested=claude/'projects/encoded/nested/no.jsonl';nested.write_bytes(b'not read')
    plan=prepare_history({'claude':claude},selected=True)
    assert [s.relative for s in plan.sources]==['projects/encoded/chat.jsonl'] and not tracker.touched([nested])


def test_filesystem_without_hardlinks_uses_exclusive_streamed_copy(tmp_path,monkeypatch):
    root,_=_source(tmp_path)
    plan=prepare_history({'codex':root},selected=True)
    import sync_core.machine.history as module
    def unsupported(*args):raise OSError(errno.ENOTSUP,'not supported')
    monkeypatch.setattr(module.os,'link',unsupported)
    paths=_paths(tmp_path,plan)
    write_history(plan,paths,parent_content_id=PARENT)
    assert validate_history(paths,parent_content_id=PARENT)


def _forge(tmp_path, body, *, relative='history.jsonl', offset=0):
    from sync_core.machine.history import _hash
    sid=_hash(['codex',relative]); member=f'files/{sid}/{offset:020d}.bin'
    entry={'source_id':sid,'agent':'codex','relative':relative,'offset':offset,'size':len(body),
           'sha256':hashlib.sha256(body).hexdigest(),'archive_path':member}
    entries=[entry]
    manifest={'format':'ai-machine-history','schema_version':1,'parent_content_id':PARENT,
              'set_id':_hash([entries]),'part_index':1,'part_count':1,'entries':entries,'content_id':_hash(entries)}
    path=tmp_path/'forged.zip'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr(member,body);archive.writestr('manifest.json',json.dumps(manifest))
    return path


@pytest.mark.parametrize('case',['secret','invalid','traversal','not_history','offset','long_line'])
def test_valid_digests_do_not_bypass_history_content_and_path_gate(tmp_path,case):
    body=b'{"message":"safe"}\n'; relative='history.jsonl';offset=0
    limits=HistoryLimits()
    if case=='secret':body=json.dumps({'message':'sk-'+'z'*30}).encode()+b'\n'
    if case=='invalid':body=b'{bad}\n'
    if case=='traversal':relative='../history.jsonl'
    if case=='not_history':relative='auth.json'
    if case=='offset':offset=3
    if case=='long_line':limits=HistoryLimits(line_bytes=10)
    path=_forge(tmp_path,body,relative=relative,offset=offset)
    with pytest.raises(HistoryError):validate_history([path],parent_content_id=PARENT,limits=limits)


def test_history_root_junction_is_not_read(tmp_path,monkeypatch):
    import subprocess
    root,_=_source(tmp_path);outside=tmp_path/'outside';outside.mkdir()
    file=outside/'chat.jsonl';file.write_bytes(b'protected')
    linked=root/'archived_sessions'
    subprocess.run(['cmd','/c','mklink','/J',str(linked),str(outside)],check=True,capture_output=True)
    tracker=ReadTracker(monkeypatch)
    plan=prepare_history({'codex':root},selected=True)
    assert not tracker.touched([file]) and any(e['reason']=='link_blocked' for e in plan.exclusions)
    linked.rmdir()


def _backup_plan(tmp_path, *, selected=True):
    from sync_core.machine.backup import prepare_backup
    from sync_core.machine.config import load_config
    root,file=_source(tmp_path)
    out=tmp_path/'out';out.mkdir(exist_ok=True)
    plan=prepare_backup(home=root.parent,config=load_config(tmp_path/'none.json',home=root.parent),out=out,
                        agents=frozenset({'codex'}),environ={},software={'versions':{}},git_keys=[],
                        groups=frozenset({'history'}) if selected else frozenset({'rules'}),
                        history_limits=HistoryLimits(part_bytes=140,chunk_bytes=70))
    return plan,file,out


def test_coordinated_backup_associates_main_and_all_parts_without_history_in_main(tmp_path):
    from sync_core.machine.backup import apply_backup
    from sync_core.machine.bundle import read_bundle
    plan,file,out=_backup_plan(tmp_path)
    preview=plan.preview();assert preview['history']['parts']>1
    assert preview['by_group']['history']['bytes']==file.stat().st_size and not list(out.iterdir())
    result=apply_backup(plan)
    main,files=read_bundle(plan.writer.destination)
    assert all(e['kind']=='report' for e in main['entries'])
    report=json.loads(files['reports/history.json'])
    paths=[out/p['name'] for p in report['packages']]
    parts=validate_history(paths,parent_content_id=main['content_id'],limits=plan.history.limits)
    assert report['set_id']==parts[0]['set_id']==result['history']['set_id']
    assert len(list(out.iterdir()))==len(paths)+1
    assert plan.writer.destination.parent==out and plan.history.verify_sources_unchanged()


def test_unselected_backup_does_not_open_history_body(tmp_path,monkeypatch):
    root,file=_source(tmp_path)
    tracker=ReadTracker(monkeypatch)
    plan,_,_=_backup_plan(tmp_path,selected=False)
    assert plan.history is None and plan.preview()['history'] is None
    assert not tracker.touched([file])


def test_coordinated_publication_failure_rolls_back_set(tmp_path,monkeypatch):
    from sync_core.machine.backup import apply_backup
    import sync_core.machine.history as module
    plan,_,out=_backup_plan(tmp_path)
    original=module.os.link
    def fail_second(source,target):
        if Path(target).parent==out and '历史-2' in Path(target).name:
            raise OSError(errno.EIO,'injected failure')
        return original(source,target)
    monkeypatch.setattr(module.os,'link',fail_second)
    with pytest.raises(OSError):apply_backup(plan)
    assert not list(out.iterdir()) and plan.writer.destination.parent==out


def test_existing_history_destination_is_preserved_and_main_not_published(tmp_path):
    from sync_core.machine.backup import apply_backup
    plan,_,out=_backup_plan(tmp_path)
    existing=out/plan.history.references(plan.writer.destination)[0]['name']
    existing.write_bytes(b'original unrelated archive')
    from sync_core.machine.bundle import BundleError
    with pytest.raises(BundleError):apply_backup(plan)
    assert existing.read_bytes()==b'original unrelated archive' and list(out.iterdir())==[existing]


def test_desktop_history_backup_rejects_raw_source_change_even_if_redacted_bytes_match(tmp_path):
    from sync_core.application.machine_protocol import MachineProtocol
    from test_machine_desktop import preview, apply
    import os
    root,file=_source(tmp_path)
    file.write_bytes(json.dumps({'message':'sk-'+'a'*30}).encode()+b'\n')
    out=tmp_path/'out';out.mkdir()
    protocol=MachineProtocol(tmp_path/'device.json',home=root.parent,environ={})
    params={'destination':str(out),'agents':['codex'],'groups':['history'],'projects':[]}
    plan=preview(protocol,'machine_backup',**params)
    assert plan['can_apply'] and plan['result']['history']['parts']==1
    assert plan['result']['flagged']['count']==1 and plan['result']['flagged']['items'][0]['rule_id']=='CX-14'
    st=file.stat()
    file.write_bytes(json.dumps({'message':'sk-'+'b'*30}).encode()+b'\n')
    os.utime(file,ns=(st.st_atime_ns,st.st_mtime_ns))
    result=apply(protocol,plan)
    assert result['error']['code']=='E_PLAN_STALE' and not list(out.iterdir())
    plan=preview(protocol,'machine_backup',**params)
    result=apply(protocol,plan)
    assert result['status']=='applied' and len(list(out.iterdir()))==2


def test_history_metadata_is_bounded_independently_of_payload(tmp_path):
    root,_=_source(tmp_path)
    with pytest.raises(HistoryError):prepare_history({'codex':root},selected=True,limits=HistoryLimits(metadata_bytes=100))
    plan=prepare_history({'codex':root},selected=True);paths=_paths(tmp_path,plan)
    write_history(plan,paths,parent_content_id=PARENT)
    with pytest.raises(HistoryError):validate_history(paths,parent_content_id=PARENT,limits=HistoryLimits(metadata_bytes=100))


def test_protected_nested_history_directories_are_pruned_before_reads(tmp_path,monkeypatch):
    root,_=_source(tmp_path);folder=root/'sessions/cache';folder.mkdir()
    protected=folder/'cache.jsonl';protected.write_bytes(b'protected')
    tracker=ReadTracker(monkeypatch)
    plan=prepare_history({'codex':root},selected=True)
    assert not tracker.touched([protected]) and any(e['reason']=='protected_history_path' for e in plan.exclusions)


@pytest.mark.parametrize('policy', ['redact', 'skip'])
def test_flag_line_samples_have_global_budget_without_losing_file_notices(tmp_path, policy):
    root, file = _source(tmp_path)
    data = (json.dumps({'message': 'sk-' + 'a' * 30}).encode() + b'\n') * 3
    file.write_bytes(data)
    second = file.with_name('second.jsonl'); second.write_bytes(data)
    third = file.with_name('third.jsonl'); third.write_bytes(data)
    plan = prepare_history({'codex': root}, selected=True, policy=policy, limits=HistoryLimits(flagged_lines=2))
    assert len(plan.flagged) == 3
    assert sum(len(item['lines']) for item in plan.flagged) == 2
    assert all(item['line_count'] >= 1 and item['lines_truncated'] == (item['line_count'] > len(item['lines'])) for item in plan.flagged)
    assert any(not item['lines'] and item['lines_truncated'] for item in plan.flagged)
    assert all(item['action'] == ('skipped' if policy == 'skip' else 'redacted') for item in plan.flagged)
    assert plan.sampled_lines == 2


def _history_bytes(tmp_path, body, *, suffix='bin', limits=None):
    root = tmp_path/'home/.codex'
    source = root/f'sessions/2026/content.{suffix}'
    source.parent.mkdir(parents=True); source.write_bytes(body)
    limits = limits or HistoryLimits(chunk_bytes=7, part_bytes=21)
    plan = prepare_history({'codex': root}, selected=True, limits=limits)
    paths = _paths(tmp_path, plan)
    write_history(plan, paths, parent_content_id=PARENT)
    manifests = validate_history(paths, parent_content_id=PARENT, limits=limits)
    output = bytearray()
    for path, manifest in zip(paths, manifests):
        with zipfile.ZipFile(path) as archive:
            for entry in manifest['entries']:
                output.extend(archive.read(entry['archive_path']))
    return plan, bytes(output)


@pytest.mark.parametrize('body', [b'\xff\x00\x01opaque\n\x00tail', b'plain text\nkeep\r\n', b'', bytes(range(128))])
def test_codex_non_jsonl_history_preserves_binary_and_text(tmp_path, body):
    plan, output = _history_bytes(tmp_path, body)
    assert output == body and len(plan.sources) == 1 and not plan.exclusions


@pytest.mark.parametrize('encoding', ['utf-16-le', 'utf-16-be', 'utf-32-le', 'utf-32-be'])
@pytest.mark.parametrize('bom', [False, True])
def test_encoded_jsonl_cross_segment_boundaries(tmp_path, encoding, bom):
    import codecs
    header = getattr(codecs, 'BOM_' + encoding.upper().replace('-', '_').replace('UTF_', 'UTF')) if bom else b''
    text = '\n' + json.dumps({'message': '中文😀 ' + 'sk-' + 'a'*30}, ensure_ascii=False) + '\r\n' + '{}\n'
    plan, output = _history_bytes(tmp_path, header + text.encode(encoding), suffix='jsonl')
    assert len(plan.sources) == 1 and plan.sources[0].redactions == 1
    assert output == header + text.replace('sk-'+'a'*30, '<REDACTED>').encode(encoding)


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16-le', 'utf-16-be', 'utf-32-le', 'utf-32-be'])
@pytest.mark.parametrize('bom', [False, True])
def test_raw_multiline_private_key_body_is_removed(tmp_path, encoding, bom):
    import codecs
    header = b'' if encoding == 'utf-8' or not bom else getattr(codecs, 'BOM_' + encoding.upper().replace('-', '_').replace('UTF_', 'UTF'))
    key = '-----BEGIN ' + 'PRIVATE KEY-----\n' + 'sensitivebody\n'*4 + '-----END ' + 'PRIVATE KEY-----'
    text = 'keep😀\n' + key + '\nkeep tail\n'
    plan, output = _history_bytes(tmp_path, header + text.encode(encoding), suffix='txt')
    assert len(plan.sources) == 1 and plan.sources[0].redactions == 1
    assert output == header + text.replace(key, '<REDACTED>').encode(encoding)
    assert plan.flagged[0]['lines'] == [2]


def test_unclosed_raw_private_key_redacts_to_eof(tmp_path):
    key = '-----BEGIN ' + 'PRIVATE KEY-----\nbody\n'
    plan, output = _history_bytes(tmp_path, ('prefix\n'+key).encode())
    assert output == b'prefix\n<REDACTED>\n' and plan.sources[0].redactions == 1


@pytest.mark.parametrize('suffix, body, reason', [
    ('json', b'{"PASSWORD": 123456789}', 'redaction_parse_failed'),
    ('toml', ('PASSWORD'+' = '+str(123456789)).encode(), 'redaction_parse_failed'),
    ('txt', ('-----BEGIN ' + 'PRIVATE KEY-----\n' + 'body\n'*30).encode(), 'private_key_block_too_long'),
])
def test_raw_structured_redaction_and_key_buffer_guards(tmp_path, suffix, body, reason):
    plan, output = _history_bytes(tmp_path, body, suffix=suffix, limits=HistoryLimits(line_bytes=100))
    assert not plan.sources and not output and plan.exclusions[0]['reason'] == reason


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16-le', 'utf-16-be', 'utf-32-le', 'utf-32-be'])
def test_forged_binary_history_cannot_bypass_credential_gate(tmp_path, encoding):
    path = _forge(tmp_path, b'\xff' + ('sk-'+'z'*30).encode(encoding), relative='sessions/data.bin')
    with pytest.raises(HistoryError):
        validate_history([path], parent_content_id=PARENT)


@pytest.mark.parametrize('suffix, body', [
    ('json', json.dumps({'PASSWORD': 'sk-'+'a'*30, 'note': 'keep'}, ensure_ascii=False).encode()),
    ('toml', ('PASSWORD = "'+'sk-'+'a'*30+'"\nnote = "keep"\n').encode()),
])
def test_raw_structured_redaction_stays_parseable(tmp_path, suffix, body):
    plan, output = _history_bytes(tmp_path, body, suffix=suffix)
    assert plan.sources[0].redactions == 1 and b'<REDACTED>' in output
    if suffix == 'json':
        assert json.loads(output) == {'PASSWORD': '<REDACTED>', 'note': 'keep'}
    else:
        import tomllib
        assert tomllib.loads(output.decode()) == {'PASSWORD': '<REDACTED>', 'note': 'keep'}


def test_structured_redaction_format_budget_is_explicit(tmp_path):
    body = json.dumps({'message': 'sk-'+'a'*30, 'notes': ['keep']*20}, indent=2).encode()
    plan, output = _history_bytes(tmp_path, body, suffix='json', limits=HistoryLimits(line_bytes=80))
    assert not plan.sources and not output and plan.exclusions[0]['reason'] == 'redaction_format_limit'


def test_raw_utf32_private_key_with_invalid_body_units_is_still_hidden(tmp_path):
    import codecs
    start = ('-----BEGIN ' + 'PRIVATE KEY-----\n').encode('utf-32-le')
    end = ('\n-----END ' + 'PRIVATE KEY-----\nkeep').encode('utf-32-le')
    body = codecs.BOM_UTF32_LE + start + b'\xff\xff\xff\xff' + end
    plan, output = _history_bytes(tmp_path, body)
    assert plan.sources[0].redactions == 1
    assert output == codecs.BOM_UTF32_LE + '<REDACTED>\nkeep'.encode('utf-32-le')
