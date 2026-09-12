import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sync_core.transaction import SyncLock, SyncBusyError
from sync_core.snapshots import create_snapshot, mark_head_confirmed, snapshot_confirmed
from sync_core.handoff import configuration_content_version
from sync_core.utils import digest


def test_lock_cannot_be_stolen_when_metadata_is_incomplete(tmp_path):
    with SyncLock(tmp_path):
        (tmp_path / "sync.lock").write_text("")
        with pytest.raises(SyncBusyError):
            with SyncLock(tmp_path):
                pass


def test_process_exit_releases_kernel_lock(tmp_path):
    code = "from pathlib import Path; import os,sys; from sync_core.transaction import SyncLock; lock=SyncLock(Path(sys.argv[1])); lock.__enter__(); os._exit(0)"
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)])
    assert result.returncode == 0
    with SyncLock(tmp_path):
        assert (tmp_path / "sync.lock").exists()


def test_old_confirmation_survives_new_pending_head(tmp_path):
    old = create_snapshot(tmp_path, device="mac", scope="project", files={"a.md": b"old"})
    mark_head_confirmed(tmp_path, "mac", "project")
    new = create_snapshot(tmp_path, device="mac", scope="project", files={"a.md": b"new"}, parent_snapshot=old["snapshot_id"])
    assert snapshot_confirmed(tmp_path, old)
    assert not snapshot_confirmed(tmp_path, new)
    receipt = tmp_path / "confirmations/mac" / f"{old['snapshot_id']}.json"
    data = json.loads(receipt.read_text())
    data["manifest_sha256"] = "wrong"
    receipt.write_text(json.dumps(data))
    assert not snapshot_confirmed(tmp_path, old)


def test_config_content_ignores_remote_progress_but_not_fields():
    facts = {"schema_version": 1, "files": {"rules": "hash"}, "codex_keys": ["web_search"], "claude_keys": [], "remote_commit": "old"}
    newer = dict(facts, remote_commit="new", branch="other", ready=False)
    assert configuration_content_version(facts) == configuration_content_version(newer)
    newer["files"] = {"rules": "changed"}
    assert configuration_content_version(facts) != configuration_content_version(newer)


def test_receiver_baseline_wins_over_sender_parent(tmp_path, monkeypatch):
    from scripts import sync
    monkeypatch.setattr(sync, "ROOT", tmp_path / "config")
    memory, native, state = [tmp_path / name for name in ("memory", "native", "state")]
    native.mkdir(); state.mkdir()
    (native / "a.md").write_bytes(b"v1")
    (state / "memory-project.json").write_text(json.dumps({"files": {"a.md": digest(b"v1")}}))
    parent = create_snapshot(memory, device="mac", scope="project", project_id="project", files={"a.md": b"v2"})
    latest = create_snapshot(memory, device="mac", scope="project", project_id="project", files={"a.md": b"v3"}, parent_snapshot=parent["snapshot_id"])
    config = {"device": "windows-b", "state_dir": str(state), "memory_repo": str(memory), "memories": [{"id": "project", "path": str(native)}], "projects": {"project": str(tmp_path)}}
    sync._start_plan(config, "project", {"ready": True, "memory_snapshot": latest["snapshot_id"]}, True, state)
    assert (native / "a.md").read_bytes() == b"v3"
