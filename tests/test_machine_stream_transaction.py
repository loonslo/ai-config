"""Large new files participate in the same journal and undo as ordinary rules."""
import hashlib
import json
from pathlib import Path

import pytest

from sync_core.streaming import StreamContent, file_digest, write_stream
from sync_core.transaction import PlannedChanges, transaction, write_file, recover_transactions
from sync_core.machine.undo import prepare_undo, undo
from sync_core.restore import RestoreError


def _content(blocks=4):
    block=b'bounded history bytes\n'*4096
    digest=hashlib.sha256()
    for _ in range(blocks):digest.update(block)
    return StreamContent(lambda: iter(block for _ in range(blocks)),digest.hexdigest(),len(block)*blocks)


def _plan(tmp_path,content):
    root=tmp_path/'home/.codex';root.mkdir(parents=True)
    normal=root/'AGENTS.md';normal.write_bytes(b'old')
    history=root/'sessions/chat.jsonl'
    state=tmp_path/'state'
    plan=PlannedChanges({normal:b'new',history:content},expected={normal:hashlib.sha256(b'old').hexdigest(),history:None},state_root=state,
                        metadata={'operation':'machine_restore','path_agents':{str(normal):'codex',str(history):'codex'},
                                  'path_boundaries':{str(normal):str(root),str(history):str(root)}})
    return plan,normal,history,state


def _forbid_whole_history_reads(monkeypatch,history):
    import importlib
    module=importlib.import_module('sync_core.transaction')
    original=module.read_bytes
    def guarded(path):
        assert path!=history,'history may not be materialized'
        return original(path)
    monkeypatch.setattr(module,'read_bytes',guarded)
    original_path_read=Path.read_bytes
    def guarded_path(path):
        assert path!=history,'history may not be materialized'
        return original_path_read(path)
    monkeypatch.setattr(Path,'read_bytes',guarded_path)


def test_large_stream_mixed_batch_commits_and_machine_undo_is_bounded(tmp_path,monkeypatch):
    content=_content(800)  # Over the main bundle's 64 MiB per-file limit.
    assert content.size>64*1024**2
    plan,normal,history,state=_plan(tmp_path,content)
    _forbid_whole_history_reads(monkeypatch,history)
    backup=transaction(plan,state/'backups',state_root=state)
    assert file_digest(history)==content.sha256 and normal.read_bytes()==b'new'
    journal=json.loads((state/'transactions'/f'{backup.name}.json').read_text())
    assert journal['status']=='COMMITTED' and journal['changes'][1]['streamed']
    selected,changes,_=prepare_undo(state,operation_id=backup.name)
    assert changes[history] is None and changes.expected[history]==content.sha256
    result=undo(state,operation_id=backup.name,apply=True,processes=[])
    assert result['mode']=='applied' and not history.exists() and normal.read_bytes()==b'old'
    undo_journal=next(json.loads(p.read_text()) for p in (state/'transactions').glob('*.json') if p.stem!=backup.name)
    stored=json.loads((Path(undo_journal['backup'])/'manifest.json').read_text())
    record=next(r for r in stored if r['path']==str(history))
    assert record['size']==content.size and (Path(undo_journal['backup'])/record['file']).stat().st_size==content.size


def test_stream_failure_rolls_back_other_files_without_publishing_partial(tmp_path):
    good=_content();bad=StreamContent(good.chunks,'0'*64,good.size)
    plan,normal,history,state=_plan(tmp_path,bad)
    with pytest.raises(ValueError,match='stream content changed'):transaction(plan,state/'backups',state_root=state)
    assert normal.read_bytes()==b'old' and not history.exists() and not list(history.parent.glob('.stream-*'))
    assert recover_transactions(state)[0]['status']=='ROLLED_BACK'


def test_committed_stream_then_later_batch_error_rolls_back_all(tmp_path,monkeypatch):
    content=_content();plan,normal,history,state=_plan(tmp_path,content)
    last=normal.parent/'later.txt';plan[last]=b'later';plan.expected[last]=None
    _forbid_whole_history_reads(monkeypatch,history)
    def fail(path,data):
        if path==last:raise OSError('injected error')
        write_file(path,data)
    with pytest.raises(OSError):transaction(plan,state/'backups',state_root=state,writer=fail)
    assert normal.read_bytes()==b'old' and not history.exists() and not last.exists()


def test_new_stream_never_overwrites_and_later_edit_blocks_undo(tmp_path):
    content=_content();plan,_,history,state=_plan(tmp_path,content)
    history.parent.mkdir();history.write_bytes(b'keep')
    with pytest.raises(ValueError,match='already exists'):transaction(plan,state/'backups',state_root=state)
    assert history.read_bytes()==b'keep'
    history.unlink()
    backup=transaction(plan,state/'backups',state_root=state)
    history.write_bytes(b'later edit')
    with pytest.raises(RestoreError):prepare_undo(state,operation_id=backup.name)
    assert history.read_bytes()==b'later edit'


def test_interruption_recovery_removes_stream_only_when_digest_matches(tmp_path,monkeypatch):
    content=_content();plan,normal,history,state=_plan(tmp_path,content)
    last=normal.parent/'later.txt';plan[last]=b'later';plan.expected[last]=None
    _forbid_whole_history_reads(monkeypatch,history)
    def interrupt(path,data):
        if path==last:raise KeyboardInterrupt()
        write_file(path,data)
    with pytest.raises(KeyboardInterrupt):transaction(plan,state/'backups',state_root=state,writer=interrupt)
    assert file_digest(history)==content.sha256 and recover_transactions(state)[0]['status']=='INTERRUPTED'
    assert recover_transactions(state,action='rollback')[0]['status']=='ROLLED_BACK'
    assert normal.read_bytes()==b'old' and not history.exists()


def test_descriptor_rejects_oversized_chunks_and_declared_size(tmp_path):
    path=tmp_path/'data'
    content=StreamContent(lambda:iter([b'x'*(1024**2+1)]),'0'*64,1024**2+1)
    with pytest.raises(ValueError,match='chunk'):write_stream(path,content)
    content=StreamContent(lambda:iter([b'xx']),'0'*64,1)
    with pytest.raises(ValueError,match='size'):write_stream(path,content)
    assert not path.exists() and not list(tmp_path.glob('.stream-*'))


def test_stream_publication_fallback_and_invalid_replace_preserve_original(tmp_path,monkeypatch):
    import errno
    import sync_core.streaming as module
    def unsupported(*args):raise OSError(errno.ENOTSUP,'unsupported')
    monkeypatch.setattr(module.os,'link',unsupported)
    content=_content();path=tmp_path/'file'
    write_stream(path,content)
    assert file_digest(path)==content.sha256
    bad=StreamContent(content.chunks,'0'*64,content.size,new_only=False)
    with pytest.raises(ValueError):write_stream(path,bad)
    assert file_digest(path)==content.sha256 and not list(tmp_path.glob('.stream-*'))


def test_interrupted_recovery_keeps_later_user_edit(tmp_path):
    content=_content();plan,normal,history,state=_plan(tmp_path,content)
    last=normal.parent/'later.txt';plan[last]=b'later';plan.expected[last]=None
    def interrupt(path,data):
        if path==last:raise KeyboardInterrupt()
        write_file(path,data)
    with pytest.raises(KeyboardInterrupt):transaction(plan,state/'backups',state_root=state,writer=interrupt)
    history.write_bytes(b'user edit')
    result=recover_transactions(state,action='rollback')[0]
    assert result['status']=='ROLLBACK_REQUIRED' and str(history) in result['rollback_conflicts']
    assert history.read_bytes()==b'user edit' and normal.read_bytes()==b'old'


def test_unexpected_writer_output_is_recorded_as_recovery_conflict(tmp_path):
    content=_content();plan,normal,history,state=_plan(tmp_path,content)
    def changed(path,data):
        if path==history:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'external edit')
            raise OSError('write interrupted')
        write_file(path,data)
    with pytest.raises(OSError):transaction(plan,state/'backups',state_root=state,writer=changed)
    journal=recover_transactions(state)[0]
    assert journal['status']=='ROLLBACK_REQUIRED' and str(history) in journal['rollback_conflicts']
    assert history.read_bytes()==b'external edit' and normal.read_bytes()==b'old'
