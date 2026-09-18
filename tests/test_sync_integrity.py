"""Regression tests for the 2026-09-17 review round.

The review found seven defects; every one of them had the same shape: the tool
reported something it had not actually done.

* the configuration source was never downloaded, and ``--fetch`` pulled the
  *memory* repository instead;
* a "仅此设备" override was written to a file nothing ever read;
* a memory-enabled device failed its own read-back check, and the failure was
  recorded as a success before it was detected;
* receipts were "uploaded" to a temporary workspace whose remote was the local
  path, so no other clone could ever see them;
* choosing ``share`` for a rules block raised ``NameError``;
* a preview consumed the one-shot restore decision;
* the test suite depended on the Windows ANSI code page.

Every scenario runs in an isolated directory with its own bare remote.  The real
tool configuration, the user's home directory and this repository's own remote
are never touched.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sync_core import config_source, config_status, config_sync, receipts, status
from sync_core.config import DeviceConfig, load as load_config

ROOT = Path(__file__).resolve().parents[1]

RULE_TOPICS = ("instructions", "principles", "engineering", "python", "langgraph", "rag", "security")


# --------------------------------------------------------------------------
# fixtures: a configuration source with a real remote
# --------------------------------------------------------------------------

def _git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if check and result.returncode:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def _write_source_tree(root: Path, *, instructions: str = "shared v1") -> None:
    for name in RULE_TOPICS:
        path = root / "common" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"shared v1" if name == "instructions" else name, encoding="utf-8")
    (root / "common" / "instructions.md").write_text(instructions, encoding="utf-8")
    (root / "codex").mkdir(parents=True, exist_ok=True)
    (root / "claude").mkdir(parents=True, exist_ok=True)
    (root / "codex" / "config.toml").write_text(
        'model_reasoning_effort = "high"\nweb_search = "cached"\n', encoding="utf-8"
    )
    (root / "claude" / "settings.shared.json").write_text('{"autoMemoryEnabled": true}\n', encoding="utf-8")
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "note.md").write_text("unrelated source document\n", encoding="utf-8")


def _commit_all(root: Path) -> None:
    _git("-C", str(root), "add", ".")
    _git("-C", str(root), "commit", "-qm", "init")


def _source_fixture(tmp_path: Path, name: str = "config-src") -> tuple[Path, Path]:
    """A configuration source checkout pushed to a bare remote.

    Returns ``(remote, checkout)``.  The remote is a real second repository, so a
    push that only "succeeds" against a local path is detected.
    """
    remote = tmp_path / "config.git"
    _git("init", "-q", "--bare", "-b", "main", str(remote))
    checkout = tmp_path / name
    _git("init", "-q", "-b", "main", str(checkout))
    _git("-C", str(checkout), "config", "user.name", "Test")
    _git("-C", str(checkout), "config", "user.email", "test@example.invalid")
    _write_source_tree(checkout)
    _commit_all(checkout)
    _git("-C", str(checkout), "remote", "add", "origin", str(remote))
    _git("-C", str(checkout), "push", "-q", "-u", "origin", "main")
    return remote, checkout


def _clone(remote: Path, destination: Path) -> Path:
    _git("clone", "-q", str(remote), str(destination))
    _git("-C", str(destination), "config", "user.name", "Test")
    _git("-C", str(destination), "config", "user.email", "test@example.invalid")
    return destination


def _device_raw(tmp_path: Path, *, codex: Path | None = None, **extra) -> dict:
    codex = codex or (tmp_path / "codex")
    codex.mkdir(exist_ok=True)
    raw = {
        "device": "windows-a",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory"),
        "codex": str(codex),
        "codex_keys": [],
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "tool_versions": {},
        "additional_sources": [],
        "memories": [],
        "projects": {},
    }
    raw.update(extra)
    return raw


def _state_for(device: str, *, version: str = "v1") -> dict:
    return status.build_state(
        device_id=device,
        source={"type": "git", "identity": "example/repo", "status": "applied"},
        capabilities={
            "config": status.capability(enabled=True, status="applied"),
            "memory": status.capability(enabled=False, status="not_configured"),
            "handoff": status.capability(enabled=False, status="not_configured"),
        },
        managed={
            "shared_fields": {"rules": ["instructions"]},
            "last_applied_version": version,
            "targets": [{
                "tool": "codex", "target": "C:/codex/AGENTS.md", "target_kind": "rules_block",
                "fields": ["rules"], "status": "applied",
                "expected_digest": "a" * 64, "observed_digest": "b" * 64, "detail": "local",
            }],
        },
    )


def _run_cli(args: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    """Run the CLI with a UTF-8 pipe on both sides of the process boundary."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd),
        env=env,
    )


def _patched_source(monkeypatch, source: Path) -> None:
    """Point both template readers at the same fixture source.

    ``scripts.sync.ROOT`` feeds the writer and ``config_sync.ROOT_FOR_TEMPLATES``
    feeds the read-back expectation; a mismatch between them is itself a bug, so
    tests always patch both.
    """
    from scripts import sync as sync_script

    monkeypatch.setattr(sync_script, "ROOT", source)
    monkeypatch.setattr(config_sync, "ROOT_FOR_TEMPLATES", source)


# --------------------------------------------------------------------------
# 高 1: the configuration source is downloaded and published separately
# --------------------------------------------------------------------------

def test_fetch_downloads_the_configuration_source_not_the_memory_repository(tmp_path):
    remote, checkout = _source_fixture(tmp_path)
    other = _clone(remote, tmp_path / "other")
    (other / "common" / "instructions.md").write_text("shared v2", encoding="utf-8")
    published = config_source.publish({"device": "mac", "config_repo": str(other)}, apply=True)
    assert published["status"] == "published", published

    memory_repo = tmp_path / "memory"
    memory_repo.mkdir()
    (memory_repo / "note.md").write_text("memory only", encoding="utf-8")
    device = _device_raw(tmp_path, config_repo=str(checkout))

    report = config_source.fetch(device)
    assert report["status"] == "updated", report
    assert (checkout / "common" / "instructions.md").read_text(encoding="utf-8") == "shared v2"
    # The memory repository is a different repository and is never the source.
    assert (memory_repo / "note.md").read_text(encoding="utf-8") == "memory only"
    assert not (memory_repo / ".git").exists()
    assert config_source.fetch(device)["status"] == "up_to_date"


def test_a_source_without_a_remote_is_reported_as_not_configured(tmp_path):
    checkout = tmp_path / "local-only"
    _git("init", "-q", "-b", "main", str(checkout))
    _git("-C", str(checkout), "config", "user.name", "Test")
    _git("-C", str(checkout), "config", "user.email", "test@example.invalid")
    _write_source_tree(checkout)
    _commit_all(checkout)
    device = _device_raw(tmp_path, config_repo=str(checkout))

    report = config_source.fetch(device)
    assert report["status"] == "not_configured"
    assert "远端" in report["detail"]


def test_publishing_preview_lists_the_files_and_writes_nothing(tmp_path):
    remote, checkout = _source_fixture(tmp_path)
    before = _git("-C", str(checkout), "rev-parse", "HEAD")
    (checkout / "common" / "instructions.md").write_text("local draft", encoding="utf-8")
    device = _device_raw(tmp_path, config_repo=str(checkout))

    preview = config_source.publish(device, apply=False)
    assert preview["status"] == "pending"
    assert preview["files"] == ["common/instructions.md"]
    assert preview["written"] is False
    assert _git("-C", str(checkout), "rev-parse", "HEAD") == before
    assert _git("-C", str(checkout), "diff", "--cached", "--name-only") == ""


def test_publishing_commits_only_the_shared_paths(tmp_path):
    remote, checkout = _source_fixture(tmp_path)
    (checkout / "common" / "instructions.md").write_text("shared v2", encoding="utf-8")
    (checkout / "docs" / "note.md").write_text("unrelated work in progress", encoding="utf-8")
    device = _device_raw(tmp_path, config_repo=str(checkout))

    result = config_source.publish(device, apply=True)
    assert result["status"] == "published", result
    assert result["files"] == ["common/instructions.md"]
    # The unrelated document is still an uncommitted local change.
    assert "docs/note.md" in _git("-C", str(checkout), "status", "--porcelain")
    # And the shared change really reached the remote.
    assert "shared v2" in _git("--git-dir", str(remote), "show", "main:common/instructions.md")


def test_publishing_never_forces_a_diverged_source(tmp_path):
    remote, checkout = _source_fixture(tmp_path)
    other = _clone(remote, tmp_path / "other")
    (other / "common" / "principles.md").write_text("remote change", encoding="utf-8")
    assert config_source.publish({"device": "mac", "config_repo": str(other)}, apply=True)["status"] == "published"

    (checkout / "common" / "instructions.md").write_text("local change", encoding="utf-8")
    with pytest.raises(config_source.ConfigSourceError) as info:
        config_source.publish(_device_raw(tmp_path, config_repo=str(checkout)), apply=True)
    assert info.value.exit_code == 4
    # The local commit is preserved instead of being thrown away or force pushed.
    assert _git("-C", str(checkout), "log", "-1", "--pretty=%s").startswith("config: publish")
    assert "local change" in _git("-C", str(checkout), "show", "HEAD:common/instructions.md")


def test_sync_downloads_publishes_and_applies_as_three_separate_facts(tmp_path):
    remote, checkout = _source_fixture(tmp_path)
    (checkout / "common" / "instructions.md").write_text("shared v2", encoding="utf-8")
    codex = tmp_path / "codex"
    raw = _device_raw(tmp_path, codex=codex, config_repo=str(checkout))
    device = tmp_path / "device.json"
    device.write_text(json.dumps(raw), encoding="utf-8")

    result = _run_cli(["sync", "--local", str(device), "--fetch", "--publish", "--apply"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "下载共享配置：" in result.stdout
    assert "远端发布：已发布" in result.stdout
    assert "本机应用：已应用" in result.stdout
    assert "shared v2" in (codex / "AGENTS.md").read_text(encoding="utf-8")
    assert "shared v2" in _git("--git-dir", str(remote), "show", "main:common/instructions.md")


# --------------------------------------------------------------------------
# 高 2: a "仅此设备" override really is what gets written
# --------------------------------------------------------------------------

def _override_device(tmp_path: Path, monkeypatch) -> tuple[DeviceConfig, Path, Path]:
    source = tmp_path / "source"
    _write_source_tree(source)
    _patched_source(monkeypatch, source)
    codex = tmp_path / "codex"
    codex.mkdir()
    raw = _device_raw(tmp_path, codex=codex, codex_keys=["model_reasoning_effort"])
    device = DeviceConfig(raw, tmp_path / "device.json")
    return device, codex / "config.toml", source


def test_a_local_override_survives_the_next_sync(tmp_path, monkeypatch):
    device, target, _source = _override_device(tmp_path, monkeypatch)

    first = config_sync.sync(device, apply=True)
    assert first["status"] == "applied" and first["verified"] is True
    assert 'model_reasoning_effort = "high"' in target.read_text(encoding="utf-8")

    saved = config_sync.plan_ownership(
        device, tool="codex", field_name="model_reasoning_effort", value="low", choice="local", apply=True
    )
    assert saved["status"] == "saved"

    second = config_sync.sync(device, apply=True)
    assert second["verified"] is True, second
    assert 'model_reasoning_effort = "low"' in target.read_text(encoding="utf-8")

    # The override is now the expected value, so a further sync is a no-op and
    # the shared "high" never comes back.
    third = config_sync.sync(device, apply=True)
    assert third["changes"] == 0, third
    assert 'model_reasoning_effort = "low"' in target.read_text(encoding="utf-8")


def test_a_local_override_is_displayed_as_the_device_value(tmp_path, monkeypatch, capsys):
    from scripts import sync as sync_script

    device, _target, _source = _override_device(tmp_path, monkeypatch)
    device_path = tmp_path / "device.json"
    device_path.write_text(json.dumps(device.raw), encoding="utf-8")
    config = load_config(device_path).raw
    config_sync.plan_ownership(
        device, tool="codex", field_name="model_reasoning_effort", value="low", choice="local", apply=True
    )

    sync_script._diff_command(config, argparse.Namespace(json=False, choice=None, apply=False), device_path)
    output = capsys.readouterr().out
    assert "来自本机覆盖" in output
    assert "共享值：high" in output
    assert "本机值：low" in output


def test_a_hand_edited_value_can_be_kept_for_this_device_only(tmp_path):
    """The exact repro from the review: edit the tool file, keep it, stay low."""
    _remote, checkout = _source_fixture(tmp_path)
    codex = tmp_path / "codex"
    raw = _device_raw(tmp_path, codex=codex, config_repo=str(checkout), codex_keys=["model_reasoning_effort"])
    device = tmp_path / "device.json"
    device.write_text(json.dumps(raw), encoding="utf-8")
    assert _run_cli(["sync", "--local", str(device), "--apply"]).returncode == 0

    target = codex / "config.toml"
    target.write_text('model_reasoning_effort = "low"\n', encoding="utf-8")

    # The diff must show the value the tool actually holds, not "（未设置）".
    shown = _run_cli(["diff", "--local", str(device)])
    assert shown.returncode == 0, shown.stdout + shown.stderr
    assert "本机值：low" in shown.stdout
    assert "共享值：high" in shown.stdout

    kept = _run_cli(["diff", "--local", str(device), "--choice", "local", "--apply"])
    assert kept.returncode == 0, kept.stdout + kept.stderr

    again = _run_cli(["sync", "--local", str(device), "--apply"])
    assert again.returncode == 0, again.stdout + again.stderr
    assert 'model_reasoning_effort = "low"' in target.read_text(encoding="utf-8")
    # The shared value is untouched: this device only.
    assert 'model_reasoning_effort = "high"' in (checkout / "codex" / "config.toml").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 高 3: write and read-back use the same effective configuration
# --------------------------------------------------------------------------

def test_a_memory_enabled_device_verifies_its_first_sync(tmp_path, monkeypatch):
    source = tmp_path / "source"
    _write_source_tree(source)
    _patched_source(monkeypatch, source)
    codex = tmp_path / "codex"
    codex.mkdir()
    memories = tmp_path / "codex-memories"
    memories.mkdir()
    device = DeviceConfig(_device_raw(tmp_path, codex=codex, codex_memory=str(memories)), tmp_path / "device.json")

    report = config_sync.sync(device, apply=True)

    assert report["status"] == "applied"
    assert report["verified"] is True, report
    written = (codex / "AGENTS.md").read_text(encoding="utf-8")
    assert "跨設備記憶" in written
    assert (device.state_dir / "applied.json").exists()


def test_a_failed_read_back_writes_no_success_record(tmp_path, monkeypatch):
    source = tmp_path / "source"
    _write_source_tree(source)
    _patched_source(monkeypatch, source)
    codex = tmp_path / "codex"
    codex.mkdir()
    device = DeviceConfig(_device_raw(tmp_path, codex=codex), tmp_path / "device.json")
    target = codex / "AGENTS.md"
    real_read = config_status._read

    def unreadable(path):
        if Path(path) == target and target.exists():
            raise config_status.TargetUnreadable("locked by the tool")
        return real_read(path)

    monkeypatch.setattr(config_status, "_read", unreadable)
    with pytest.raises(config_sync.ConfigSyncError) as info:
        config_sync.sync(device, apply=True)

    assert info.value.stage == "verify"
    assert info.value.exit_code == 2
    # The write happened, the verification did not pass, so no success record.
    assert target.exists()
    assert not (device.state_dir / "applied.json").exists()


def test_a_target_matching_an_older_version_is_not_verified():
    assert config_sync._targets_verified([{"status": "pending_sync", "fields": ["rules"]}]) is False
    assert config_sync._targets_verified([{"status": "applied", "fields": ["rules"]}]) is True
    # A target whose managed selection is empty has nothing to verify.
    assert config_sync._targets_verified([{"status": "pending_sync", "fields": []}]) is True
    assert config_sync._targets_verified([{"status": "not_configured", "fields": []}]) is True


# --------------------------------------------------------------------------
# 高 4: receipts reach the real remote
# --------------------------------------------------------------------------

def test_a_receipt_published_from_one_clone_is_readable_in_another(tmp_path):
    remote, checkout = _source_fixture(tmp_path)
    other = _clone(remote, tmp_path / "other")

    result = receipts.publish_receipt(checkout, _state_for("windows-a"))

    assert result["status"] == "uploaded"
    assert result["branch"] == receipts.RECEIPT_BRANCH
    # The branch really exists on the remote, so a second clone can read it.
    assert receipts.RECEIPT_BRANCH in _git("--git-dir", str(remote), "branch", "--list")
    assert [item["device_id"] for item in receipts.fetch_receipts(other)] == ["windows-a"]


def test_a_source_without_a_remote_never_claims_an_upload(tmp_path):
    checkout = tmp_path / "local-only"
    _git("init", "-q", "-b", "main", str(checkout))
    _git("-C", str(checkout), "config", "user.name", "Test")
    _git("-C", str(checkout), "config", "user.email", "test@example.invalid")
    _write_source_tree(checkout)
    _commit_all(checkout)

    with pytest.raises(receipts.ReceiptUnavailable):
        receipts.publish_receipt(checkout, _state_for("windows-a"))
    assert receipts.fetch_receipts(checkout) == []


def test_sync_uploads_a_receipt_and_status_reads_it_from_the_source(tmp_path):
    remote, checkout = _source_fixture(tmp_path)
    codex = tmp_path / "codex"
    raw = _device_raw(tmp_path, codex=codex, config_repo=str(checkout), remote_identity=str(remote))
    device = tmp_path / "device.json"
    device.write_text(json.dumps(raw), encoding="utf-8")

    applied = _run_cli(["sync", "--local", str(device), "--apply"])
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert "状态上报：已上报" in applied.stdout

    listing = _run_cli(["status", "--local", str(device), "--json"])
    assert listing.returncode == 0, listing.stderr
    payload = json.loads(listing.stdout)
    assert [row["device_id"] for row in payload["receipts"]] == ["windows-a"]


# --------------------------------------------------------------------------
# 中 5: sharing a rules block stages the content and keeps the conflict
# --------------------------------------------------------------------------

def _hand_edited_device(tmp_path, monkeypatch) -> tuple[DeviceConfig, Path]:
    source = tmp_path / "source"
    _write_source_tree(source)
    _patched_source(monkeypatch, source)
    codex = tmp_path / "codex"
    codex.mkdir()
    device = DeviceConfig(_device_raw(tmp_path, codex=codex), tmp_path / "device.json")
    config_sync.sync(device, apply=True)
    agents = codex / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    agents.write_text(
        text.replace("<!-- ai-config:end -->", "\n本机额外规则。\n<!-- ai-config:end -->", 1), encoding="utf-8"
    )
    return device, agents


def test_sharing_a_rules_block_stages_it_without_claiming_the_share(tmp_path, monkeypatch):
    device, _agents = _hand_edited_device(tmp_path, monkeypatch)
    drift = config_sync.local_drift(device)

    result = config_sync.plan_rules_ownership(
        device, tool="codex", choice="share", apply_choice=True, drifting=drift["drifting"]
    )

    assert result["status"] == "pending_publish", result
    staged = Path(result["staged_content"])
    assert staged.exists()
    assert "本机额外规则。" in staged.read_text(encoding="utf-8")
    # Nothing was published and no baseline was refreshed: the divergence has to
    # stay visible until the shared source really produces this block.
    assert result["committed_files"] == ["common/"]
    with pytest.raises(config_sync.ConfigSyncError) as info:
        config_sync.sync(device, apply=True)
    assert info.value.exit_code == 4


def test_merging_the_shared_block_closes_the_share_loop(tmp_path, monkeypatch):
    from scripts import sync as sync_script

    device, _agents = _hand_edited_device(tmp_path, monkeypatch)
    drift = config_sync.local_drift(device)
    staged = Path(
        config_sync.plan_rules_ownership(
            device, tool="codex", choice="share", apply_choice=True, drifting=drift["drifting"]
        )["staged_content"]
    ).read_bytes()

    # A human merges the staged block into common/; the tool cannot split an
    # aggregated block back into topic files, so the fixture simulates the merge
    # by making the source produce exactly the merged block.
    monkeypatch.setattr(sync_script, "_body", lambda config=None: staged)
    report = config_sync.sync(device, apply=True)
    assert report["status"] == "applied" and report["verified"] is True, report
    # The loop is closed: a further sync is a no-op, not another conflict.
    assert config_sync.sync(device, apply=True)["changes"] == 0


# --------------------------------------------------------------------------
# 中 6: a preview never consumes the restore decision
# --------------------------------------------------------------------------

def _cli_drift_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """A synced device whose managed rules block was then hand-edited."""
    codex = tmp_path / "codex"
    codex.mkdir()
    device = tmp_path / "device.json"
    device.write_text(json.dumps(_device_raw(tmp_path, codex=codex)), encoding="utf-8")
    agents = codex / "AGENTS.md"
    agents.write_text("# 本机说明\n\n用户自己的内容。\n", encoding="utf-8")
    first = _run_cli(["sync", "--local", str(device), "--apply"])
    assert first.returncode == 0, first.stderr
    text = agents.read_text(encoding="utf-8")
    agents.write_text(
        text.replace("<!-- ai-config:end -->", "\n本机额外加的一条规则。\n<!-- ai-config:end -->", 1), encoding="utf-8"
    )
    return device, agents


def test_a_preview_does_not_consume_the_restore_decision(tmp_path):
    device, agents = _cli_drift_fixture(tmp_path)
    marker = Path(json.loads(device.read_text(encoding="utf-8"))["state_dir"]) / "codex-rules-accept-shared.json"

    resolved = _run_cli(["diff", "--local", str(device), "--choice", "restore", "--apply"])
    assert resolved.returncode == 0, resolved.stdout + resolved.stderr
    assert marker.exists()

    preview = _run_cli(["sync", "--local", str(device)])
    assert preview.returncode == 2, preview.stdout + preview.stderr
    assert marker.exists(), "预览不应消耗恢复决定"

    applied = _run_cli(["sync", "--local", str(device), "--apply"])
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert not marker.exists(), "成功应用后才应清除恢复决定"
    assert "本机额外加的一条规则。" not in agents.read_text(encoding="utf-8")
    assert "用户自己的内容。" in agents.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 中 7: the output encoding does not depend on the host locale
# --------------------------------------------------------------------------

def test_piped_output_is_utf8_without_a_locale_override(tmp_path):
    codex = tmp_path / "codex"
    codex.mkdir()
    device = tmp_path / "device.json"
    device.write_text(json.dumps(_device_raw(tmp_path, codex=codex)), encoding="utf-8")
    # No PYTHONIOENCODING: on Windows the child would otherwise use the ANSI code
    # page and every Chinese assertion would decode to noise.
    env = {key: value for key, value in os.environ.items() if key != "PYTHONIOENCODING"}

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync.py"), "sync", "--local", str(device)],
        capture_output=True,
        cwd=str(ROOT),
        env=env,
    )

    assert result.returncode in {0, 2}, result.stderr.decode("utf-8", "replace")
    text = result.stdout.decode("utf-8")
    assert "这是预览，没有写入任何文件" in text
    assert "下载共享配置：" in text
