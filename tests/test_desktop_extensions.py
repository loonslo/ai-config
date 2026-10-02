"""Selected core scenarios for the final desktop implementation pass."""
from __future__ import annotations
import json
from pathlib import Path
import zipfile

import pytest

from sync_core import agents
from sync_core.application.protocol import ApplicationProtocol
from sync_core.package.extensions import capture, collect_extensions, normalize_mcp, read_skill
from sync_core.package.export import build_package_manifest, export_archive
from sync_core.package.policy import CollectionReport, collect_portable_config, select_portable_sources
from sync_core.package.importer import PackageImportService
from sync_core.restore import restore


def fixture(tmp_path):
    root = tmp_path / "agent"
    (root / "skills" / "example").mkdir(parents=True)
    (root / "skills/example/SKILL.md").write_text("# example\nUse clear function boundaries.\n", encoding="utf-8")
    store = tmp_path / "store"
    store.mkdir()
    config = {"device": "receiver", "codex": str(root), "config_repo": str(store), "state_dir": str(tmp_path / "state"), "memory_repo": str(tmp_path / "memory"), "codex_keys": [], "claude_keys": [], "agents": {}}
    local = tmp_path / "device.json"
    local.write_text(json.dumps(config), encoding="utf-8")
    return root, store, config, local


def archive(tmp_path, report):
    manifest, objects = build_package_manifest(report)
    target = tmp_path / "sample.aiconfig"
    with zipfile.ZipFile(target, "w") as zipped:
        zipped.writestr("manifest.json", json.dumps(manifest))
        for name, data in objects.items():
            zipped.writestr(name, data)
    return target


def test_selected_skill_capture_import_deploy_and_undo(tmp_path):
    root, store, config, local = fixture(tmp_path)
    data, plan = capture(config, store, kind="skills", profile="codex", name="example", source=root / "skills/example", apply=True)
    assert data["status"] == "captured"
    collected = collect_extensions(store, CollectionReport((), (), (), (), 0), ["skills"])
    target = archive(tmp_path, collected)
    # Simulate a receiving device without taking over the source agent.
    receiver = tmp_path / "receiver"
    receiver.mkdir()
    config["codex"] = str(receiver)
    local.write_text(json.dumps(config), encoding="utf-8")
    host = agents.HostEnv.for_home(tmp_path, system="windows", environ={}, which=lambda _name: None)
    importer = PackageImportService(local, host=host)
    preview = importer.preview(target)
    assert preview.status == "ready"
    result = importer.apply(preview.plan_id)
    assert (receiver / "skills/example/SKILL.md").read_bytes() == (root / "skills/example/SKILL.md").read_bytes()
    restore(Path(config["state_dir"]), operation_id=result["operation_id"], apply=True)
    assert not (receiver / "skills/example/SKILL.md").exists()
    assert (root / "skills/example/SKILL.md").exists()


def test_capture_preview_invalidated_by_source_edit(tmp_path):
    root, store, config, local = fixture(tmp_path)
    protocol = ApplicationProtocol(local)
    preview = protocol.handle({"protocol_version": 1, "request_id": "preview", "type": "preview", "operation": "extension_capture", "params": {"kind": "skills", "profile": "codex", "name": "example", "source": str(root / "skills/example")}})
    assert preview["can_apply"]
    (root / "skills/example/SKILL.md").write_text("# newer\n", encoding="utf-8")
    result = protocol.handle({"protocol_version": 1, "request_id": "apply", "type": "apply", "plan_id": preview["plan_id"]})
    assert result["error"]["code"] == "E_PLAN_STALE"
    assert not (store / "portable").exists()


def test_mcp_rejects_inline_secrets_and_machine_commands():
    for value in ({"command": "tool", "env": {"AUTH_TOKEN": "not-a-real-credential"}},
                  {"command": "C:\\tools\\tool.exe"}, {"url": "https://example.invalid/?token=sample"},
                  {"command": "tool", "args": ["--directory=/opt/local"]}):
        with pytest.raises(ValueError):
            normalize_mcp(value)
    assert normalize_mcp({"command": "tool", "env_vars": ["SERVICE_AUTH"]}) == {"command": "tool", "env_vars": ["SERVICE_AUTH"]}


def test_scope_disabled_never_reads_portable_content(tmp_path, monkeypatch):
    root, store, config, local = fixture(tmp_path)
    forbidden = store / "portable/skills/codex/example/SKILL.md"
    forbidden.parent.mkdir(parents=True)
    forbidden.write_text("# not selected\n", encoding="utf-8")
    from sync_core.package import extensions
    def fail(*_args, **_kwargs):
        raise AssertionError("unselected extension was read")
    monkeypatch.setattr(extensions, "collect_extensions", fail)
    report = collect_portable_config(config, store, extension_kinds=[])
    assert not any(item.data_type == "skill_file" for item in report.entries)


def test_external_skill_link_is_rejected(tmp_path):
    boundary = tmp_path / "skills"
    boundary.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text("# private\n")
    link = boundary / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS account cannot create symlinks")
    with pytest.raises(ValueError, match="越出"):
        read_skill(link, boundary)


def test_export_with_unselected_extension_uses_valid_exclusion(tmp_path):
    root, store, config, local = fixture(tmp_path)
    (store / "common").mkdir()
    (store / "common/instructions.md").write_text("# shared\n", encoding="utf-8")
    capture(config, store, kind="skills", profile="codex", name="example", source=root / "skills/example", apply=True)
    collected = collect_portable_config(config, store, extension_kinds=["skills"])
    sources = [entry.logical_source for entry in collected.entries if entry.data_type != "skill_file"]
    report = select_portable_sources(collected, sources)
    result = export_archive(report, tmp_path / "excluded.aiconfig", config=config, store_root=store, selected_sources=sources)
    assert result.path.exists()


def test_portable_claude_memory_capture_restore_without_git(tmp_path):
    from sync_core.snapshots import create_snapshot
    from sync_core.application.service import ApplicationService
    root, store, config, local = fixture(tmp_path)
    repo = Path(config["memory_repo"])
    snapshot = create_snapshot(repo, device="source", scope="demo", project_id="demo", tool="claude", files={"MEMORY.md": b"# Project facts\nUse small modules.\n"})
    source = repo / "snapshots/source" / f"{snapshot['snapshot_id']}.json"
    result, _ = capture(config, store, kind="memory", profile="claude", name="demo", source=source, apply=True)
    target = tmp_path / "claude-project-memory"
    target.mkdir()
    (target / "MEMORY.md").write_text("# Local original\n")
    config["memories"] = [{"id": "demo", "path": str(target)}]
    local.write_text(json.dumps(config))
    service = ApplicationService(local)
    preview = service.portable_restore(project_id="demo", profile="claude")
    assert preview.data["can_apply"]
    assert (target / "MEMORY.md").read_text() == "# Local original\n"
    applied = service.portable_restore(project_id="demo", profile="claude", apply=True)
    assert applied.data["written"]
    assert (target / "MEMORY.md").read_bytes() == b"# Project facts\nUse small modules.\n"
    with pytest.raises(ValueError):
        service.portable_restore(project_id="demo", profile="codex", apply=True)


def test_portable_handoff_view_without_git_reports_missing_source_and_dependencies(tmp_path, monkeypatch):
    import hashlib
    from sync_core.application.service import ApplicationService
    from sync_core import handoff
    root, store, config, local = fixture(tmp_path)
    repo = Path(config["memory_repo"])
    source = repo / "handoffs/demo/handoff-one.json"
    source.parent.mkdir(parents=True)
    document = b"# Goal\nContinue the local project.\n"
    source.with_suffix(".md").write_bytes(document)
    record = {"schema_version": 1, "project_id": "demo", "handoff_id": "handoff-one",
              "document_sha256": hashlib.sha256(document).hexdigest(), "memory_snapshot": "snapshot-one",
              "code": {"commit": "a" * 40, "branch": "main", "lock_files": {"requirements.txt": "b" * 64}}}
    source.write_text(json.dumps(record), encoding="utf-8")
    capture(config, store, kind="handoffs", profile="claude", name="demo", source=source, apply=True)
    def no_network_or_git(*_args, **_kwargs):
        raise AssertionError("unmapped reference must not query Git or network")
    monkeypatch.setattr(handoff, "_git", no_network_or_git)
    service = ApplicationService(local)
    listed = service.portable_project(project_id="demo", profile="claude").data
    assert listed["handoffs"][0]["handoff_id"] == "handoff-one"
    report = service.portable_project(project_id="demo", profile="claude", handoff_id="handoff-one").data
    assert not report["ready"] and report["document"] == document.decode()
    assert "尚未映射本机源码工作区" in report["missing"]
    assert report["reference"]["lock_files"] == {"requirements.txt": "b" * 64}
    monkeypatch.setattr(handoff, "_git", lambda *_args, **_kwargs: "")
    project = tmp_path / "mapped-project"
    project.mkdir()
    config["projects"] = {"demo": str(project)}
    local.write_text(json.dumps(config))
    mapped = service.portable_project(project_id="demo", profile="claude", handoff_id="handoff-one").data
    assert "依赖锁文件缺失或不同：requirements.txt" in mapped["missing"]
    assert not mapped["ready"] and not (project / "requirements.txt").exists()
