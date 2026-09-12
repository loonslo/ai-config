"""Regressions from the September 12 reliability review."""
import subprocess

import pytest

from sync_core.transaction import transaction, write_file
from sync_core.transport import GitTransport
from sync_core.handoff import load_handoff
from sync_core.snapshots import create_snapshot, load_snapshot
from sync_core.transaction import recover_transactions
import json
import os
from sync_core.utils import process_is_alive


def test_edit_during_batch_is_not_overwritten(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"old-a")
    b.write_bytes(b"old-b")

    def writer(path, data):
        write_file(path, data)
        if path == a and data == b"new-a":
            b.write_bytes(b"external-edit")

    with pytest.raises(ValueError, match="newer"):
        transaction({a: b"new-a", b: b"new-b"}, tmp_path / "backups", writer=writer)
    assert b.read_bytes() == b"external-edit"
    assert a.read_bytes() == b"old-a"


def test_interrupted_transaction_blocks_next_apply(tmp_path):
    target = tmp_path / "a"
    target.write_bytes(b"old")

    def interrupt(path, data):
        write_file(path, data)
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        transaction({target: b"new"}, tmp_path / "backups", writer=interrupt)
    with pytest.raises(RuntimeError, match="transaction"):
        transaction({target: b"next"}, tmp_path / "backups")
    assert target.read_bytes() == b"new"


def test_staged_private_state_cannot_be_committed(tmp_path):
    repo = tmp_path / "repo"
    transport = GitTransport(repo)
    transport.init()
    for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid")):
        subprocess.run(["git", "-C", str(repo), "config", key, value], check=True)
    private = repo / ".ai-sync" / "state.json"
    private.parent.mkdir()
    private.write_text("{}")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    with pytest.raises(ValueError, match="staged"):
        transport.commit_pending()


def test_handoff_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError, match="Invalid"):
        load_handoff(tmp_path, "../outside", "abc")


def test_snapshot_lookup_does_not_fall_back_to_other_device(tmp_path):
    snapshot = create_snapshot(tmp_path, device="mac", scope="project", files={"a.md": b"note"})
    with pytest.raises(ValueError, match="requested device"):
        load_snapshot(tmp_path, snapshot["snapshot_id"], device="windows-a")


def test_recovery_rejects_corrupt_backup(tmp_path):
    target = tmp_path / "a"
    target.write_bytes(b"old")

    def interrupt(path, data):
        write_file(path, data)
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        transaction({target: b"new"}, tmp_path / "backups", writer=interrupt)
    backup = next((tmp_path / "backups").iterdir())
    (backup / "0").write_bytes(b"corrupted")
    result = recover_transactions(tmp_path, action="rollback")
    assert result[0]["status"] == "ROLLBACK_REQUIRED"
    assert target.read_bytes() == b"new"


def test_current_process_probe_is_read_only():
    assert process_is_alive(os.getpid())
    assert not process_is_alive(-1)
