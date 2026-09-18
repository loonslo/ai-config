import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import pytest

from sync_core.transport import GitTransport, TransportPending

spec = importlib.util.spec_from_file_location("transport", Path(__file__).parents[1] / "scripts/git-memory.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


def test_git_transport_with_local_bare_remote(tmp_path, monkeypatch):
    monkeypatch.setattr(transport.sync, "ROOT", tmp_path / "config-source")
    remote, a, b = (tmp_path / name for name in ("remote.git", "a", "b"))
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    config = tmp_path / "device.json"
    config.write_text(json.dumps({"memory_repo": str(a)}))
    def run(action):
        monkeypatch.setattr(sys, "argv", ["git-memory.py", action, "--local", str(config)])
        transport.main()
    run("init")
    transport.git(a, "config", "user.name", "Sync Test")
    transport.git(a, "config", "user.email", "sync@example.invalid")
    transport.git(a, "remote", "add", "origin", str(remote))
    memory = a / "claude/project/MEMORY.md"
    memory.parent.mkdir(parents=True)
    memory.write_text("first")
    run("push")
    subprocess.run(["git", "clone", str(remote), str(b)], check=True, capture_output=True)
    memory.write_text("second")
    run("push")
    config.write_text(json.dumps({"memory_repo": str(b)}))
    run("pull")
    assert (b / "claude/project/MEMORY.md").read_text() == "second"
    config.write_text(json.dumps({"memory_repo": str(a)}))
    memory.unlink()
    run("push")
    config.write_text(json.dumps({"memory_repo": str(b)}))
    run("pull")
    assert not (b / "claude/project/MEMORY.md").exists()


def _init_memory_repo(path, remote):
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Sync Test"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "sync@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", str(remote)], check=True)


def test_transport_fetches_remote_before_fast_forward_and_accepts_remote_ahead(tmp_path):
    remote, a, b = (tmp_path / name for name in ("remote.git", "a", "b"))
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    _init_memory_repo(a, remote)
    (a / "claude/project").mkdir(parents=True)
    (a / "claude/project/MEMORY.md").write_text("base")
    assert GitTransport(a).push_confirmed().status == "uploaded"
    subprocess.run(["git", "clone", str(remote), str(b)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(b), "config", "user.name", "Sync Test"], check=True)
    subprocess.run(["git", "-C", str(b), "config", "user.email", "sync@example.invalid"], check=True)
    (b / "claude/project/MEMORY.md").write_text("remote ahead")
    subprocess.run(["git", "-C", str(b), "add", "."], check=True)
    subprocess.run(["git", "-C", str(b), "commit", "-m", "remote update"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(b), "push", "origin", "main"], check=True, capture_output=True)
    result = GitTransport(a).push_confirmed()
    assert result.status == "uploaded"
    assert (a / "claude/project/MEMORY.md").read_text() == "remote ahead"


def test_transport_preserves_local_commit_on_true_divergence(tmp_path):
    remote, a, b = (tmp_path / name for name in ("remote.git", "a", "b"))
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    _init_memory_repo(a, remote)
    (a / "claude/project").mkdir(parents=True)
    (a / "claude/project/MEMORY.md").write_text("base")
    GitTransport(a).push_confirmed()
    subprocess.run(["git", "clone", str(remote), str(b)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(b), "config", "user.name", "Sync Test"], check=True)
    subprocess.run(["git", "-C", str(b), "config", "user.email", "sync@example.invalid"], check=True)
    (b / "claude/project/MEMORY.md").write_text("remote branch")
    subprocess.run(["git", "-C", str(b), "add", "."], check=True)
    subprocess.run(["git", "-C", str(b), "commit", "-m", "remote branch"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(b), "push", "origin", "main"], check=True, capture_output=True)
    (a / "claude/project/MEMORY.md").write_text("local branch")
    with pytest.raises(TransportPending):
        GitTransport(a).push_confirmed()
    assert (a / "claude/project/MEMORY.md").read_text() == "local branch"
    assert subprocess.check_output(["git", "-C", str(a), "log", "-1", "--format=%s"], text=True, encoding="utf-8", errors="replace").strip() == "Sync automatic memory"


def test_git_memory_cli_returns_pending_exit_code_on_divergence(tmp_path):
    # The CLI intentionally rejects repositories below the ai-config checkout;
    # place this subprocess fixture beside the checkout, not inside it.
    external = Path(tempfile.mkdtemp(prefix="ai-sync-cli-", dir=str(Path(__file__).resolve().parents[2])))
    remote, a, b = (external / name for name in ("remote.git", "a", "b"))
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    _init_memory_repo(a, remote)
    (a / "claude/project").mkdir(parents=True)
    (a / "claude/project/MEMORY.md").write_text("base")
    GitTransport(a).push_confirmed()
    subprocess.run(["git", "clone", str(remote), str(b)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(b), "config", "user.name", "Sync Test"], check=True)
    subprocess.run(["git", "-C", str(b), "config", "user.email", "sync@example.invalid"], check=True)
    (b / "claude/project/MEMORY.md").write_text("remote")
    subprocess.run(["git", "-C", str(b), "add", "."], check=True)
    subprocess.run(["git", "-C", str(b), "commit", "-m", "remote"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(b), "push", "origin", "main"], check=True, capture_output=True)
    (a / "claude/project/MEMORY.md").write_text("local")
    config = external / "device.json"
    config.write_text(json.dumps({"memory_repo": str(a), "state_dir": str(external / "state")}))
    script = Path(__file__).parents[1] / "scripts/git-memory.py"
    result = subprocess.run(["python", str(script), "push", "--local", str(config)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 3
    assert json.loads((external / "state/transport.json").read_text())["status"] == "pending"
    shutil.rmtree(external, ignore_errors=True)
