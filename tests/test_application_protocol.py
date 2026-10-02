from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from sync_core.application.protocol import PARAMETERS, ApplicationProtocol, JobControl
from sync_core.application.service import ApplicationResult


def _protocol_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    from sync_core.config import SHARED_RULE_TOPICS

    template_root = tmp_path / "templates"
    common = template_root / "common"
    common.mkdir(parents=True)
    for topic in SHARED_RULE_TOPICS:
        (common / f"{topic}.md").write_text(f"# {topic}\n", encoding="utf-8")
    codex = tmp_path / "codex"
    codex.mkdir()
    local = tmp_path / "device.json"
    local.write_text(json.dumps({
        "device": "windows-a",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory-repo"),
        "codex": str(codex),
    }), encoding="utf-8")
    return local, template_root, codex / "AGENTS.md"


def test_protocol_rejects_unknown_versions_operations_and_parameters(tmp_path):
    protocol = ApplicationProtocol(tmp_path / "device.json")
    version = protocol.handle({"protocol_version": 99, "request_id": "a", "type": "preview", "operation": "status"})
    unknown = protocol.handle({"protocol_version": 1, "request_id": "b", "type": "preview", "operation": "shell"})
    extra = protocol.handle({"protocol_version": 1, "request_id": "c", "type": "preview", "operation": "status", "params": {"command": "whoami"}})

    assert version["error"]["code"] == "E_PROTOCOL_VERSION"
    assert unknown["error"]["code"] == "E_OPERATION_UNKNOWN"
    assert extra["error"]["code"] == "E_PARAMS_UNKNOWN"


def test_setup_protocol_accepts_only_named_absolute_agent_path_overrides(tmp_path):
    valid = ApplicationProtocol.validate_request({
        "protocol_version": 1,
        "request_id": "setup-valid",
        "type": "preview",
        "operation": "setup",
        "params": {"tools": ["codex"], "tool_roots": {"codex": str(tmp_path / "custom-codex")}},
    })
    assert valid[2]["tool_roots"]["codex"] == str(tmp_path / "custom-codex")

    import pytest
    from sync_core.application.protocol import ProtocolError

    with pytest.raises(ProtocolError, match="tool_roots"):
        ApplicationProtocol.validate_request({
            "protocol_version": 1,
            "request_id": "setup-invalid",
            "type": "preview",
            "operation": "setup",
            "params": {"tools": ["codex"], "tool_roots": {"codex": "relative/path"}},
        })
    with pytest.raises(ProtocolError, match="store_path"):
        ApplicationProtocol.validate_request({
            "protocol_version": 1,
            "request_id": "setup-relative-store",
            "type": "preview",
            "operation": "setup",
            "params": {"store_path": "relative/store"},
        })


def test_package_import_protocol_accepts_only_bounded_conflict_maps(tmp_path):
    import pytest
    from sync_core.application.protocol import ProtocolError

    valid = ApplicationProtocol.validate_request({
        "protocol_version": 1,
        "request_id": "package-import-valid",
        "type": "preview",
        "operation": "package_import",
        "params": {
            "package_path": str(tmp_path / "portable.aiconfig"),
            "decisions": {"store:agent://shared/common/instructions.md": "use_package"},
            "manual_values": {"agent://shared/common/instructions.md": "# merged\n"},
            "selections": {"workbuddy:1": "workbuddy"},
            "apply_to_agents": False,
        },
    })
    assert valid[1] == "package_import"
    assert ApplicationProtocol._can_apply("package_import", {}, {"can_apply": True}) is True
    assert ApplicationProtocol._can_apply("package_import", {}, {"can_apply": False}) is False

    with pytest.raises(ProtocolError, match="package_path"):
        ApplicationProtocol.validate_request({
            "protocol_version": 1,
            "request_id": "package-import-relative",
            "type": "preview",
            "operation": "package_import",
            "params": {"package_path": "portable.aiconfig"},
        })
    with pytest.raises(ProtocolError, match="decisions"):
        ApplicationProtocol.validate_request({
            "protocol_version": 1,
            "request_id": "package-import-choice",
            "type": "preview",
            "operation": "package_import",
            "params": {
                "package_path": str(tmp_path / "portable.aiconfig"),
                "decisions": {"anything": "last_write_wins"},
            },
        })


def test_package_export_protocol_requires_absolute_target_and_supported_format(tmp_path):
    import pytest
    from sync_core.application.protocol import ProtocolError

    request = {
        "protocol_version": 1,
        "request_id": "package-export-valid",
        "type": "preview",
        "operation": "package_export",
        "params": {"destination": str(tmp_path / "portable.aiconfig"), "format": "archive"},
    }
    assert ApplicationProtocol.validate_request(request)[1] == "package_export"
    assert ApplicationProtocol._can_apply("package_export", {}, {"can_apply": True}) is True

    with pytest.raises(ProtocolError, match="destination"):
        ApplicationProtocol.validate_request({**request, "params": {"destination": "relative.aiconfig", "format": "archive"}})
    with pytest.raises(ProtocolError, match="format"):
        ApplicationProtocol.validate_request({**request, "params": {"destination": str(tmp_path / "portable.aiconfig"), "format": "zip"}})
def test_setup_uses_the_selected_custom_agent_root(tmp_path, monkeypatch):
    from sync_core import environment, wizard
    from sync_core.application.service import ApplicationService

    default_root = tmp_path / "detected"
    custom_root = tmp_path / "selected"
    monkeypatch.setattr(environment, "detect", lambda **_kwargs: {
        "ready": True,
        "tools": [{"tool": "codex", "installed": True, "root": str(default_root)}],
    })
    observed: dict[str, object] = {}

    def fake_plan_device(**kwargs):
        observed.update(kwargs)
        return {"device": "test-device", "codex": kwargs["tool_roots"]["codex"]}

    monkeypatch.setattr(wizard, "plan_device", fake_plan_device)
    result = ApplicationService(tmp_path / "device.json").setup(
        tools=["codex"],
        tool_roots={"codex": str(custom_root)},
        state_dir=tmp_path / "state",
        memory_repo=tmp_path / "memory",
    )

    assert result.data["ready"] is True
    assert observed["tool_roots"] == {"codex": str(custom_root)}
    assert result.data["config"]["codex"] == str(custom_root)


def test_migration_preview_is_not_applyable_until_a_specific_choice_is_selected():
    assert ApplicationProtocol._can_apply("migrate", {}, {"items": [{"id": "one"}]}) is False
    assert ApplicationProtocol._can_apply("migrate", {"item": "one"}, {}) is False
    assert ApplicationProtocol._can_apply("migrate", {"item": "one", "choice": "adopt"}, {}) is True


def test_setup_preview_cannot_replace_an_existing_device_config(tmp_path):
    class SetupService:
        def setup(self, **_kwargs):
            return ApplicationResult(data={"ready": True, "status": "preview", "written": False})

    local = tmp_path / "device.json"
    local.write_text("{}", encoding="utf-8")
    protocol = ApplicationProtocol(local, service_factory=lambda _path, _root: SetupService())
    result = protocol.handle({
        "protocol_version": 1,
        "request_id": "setup-no-overwrite",
        "type": "preview",
        "operation": "setup",
    })

    assert result["can_apply"] is False
    assert result["result"]["status"] == "already_configured"
    assert "不会覆盖" in result["result"]["reason"]


def test_shared_rule_edit_is_previewed_then_saved_with_backup(tmp_path):
    local, templates, _target = _protocol_fixture(tmp_path)
    from sync_core.config import SHARED_RULE_TOPICS

    store = tmp_path / "store"
    common = store / "common"
    common.mkdir(parents=True)
    for topic in SHARED_RULE_TOPICS:
        (common / f"{topic}.md").write_text(f"# {topic}\n", encoding="utf-8")
    raw = json.loads(local.read_text(encoding="utf-8"))
    raw["config_repo"] = str(store)
    local.write_text(json.dumps(raw), encoding="utf-8")
    protocol = ApplicationProtocol(local, template_root=templates)
    target = common / "instructions.md"
    before = target.read_bytes()

    preview = protocol.handle({
        "protocol_version": 1,
        "request_id": "rule-save-preview",
        "type": "preview",
        "operation": "save_rule",
        "params": {"topic": "instructions", "content": "# New shared rule\n"},
    })
    assert preview["can_apply"] is True
    assert target.read_bytes() == before

    target.write_text("# External change\n", encoding="utf-8")
    stale = protocol.handle({
        "protocol_version": 1,
        "request_id": "rule-save-stale",
        "type": "apply",
        "plan_id": preview["plan_id"],
    })
    assert stale["error"]["code"] == "E_PLAN_STALE"
    assert target.read_text(encoding="utf-8") == "# External change\n"

    preview = protocol.handle({
        "protocol_version": 1,
        "request_id": "rule-save-current-preview",
        "type": "preview",
        "operation": "save_rule",
        "params": {"topic": "instructions", "content": "# New shared rule\n"},
    })

    applied = protocol.handle({
        "protocol_version": 1,
        "request_id": "rule-save-apply",
        "type": "apply",
        "plan_id": preview["plan_id"],
    })
    assert applied["status"] == "applied"
    assert target.read_text(encoding="utf-8") == "# New shared rule\n"
    assert Path(applied["result"]["backup"]).is_dir()


def test_rule_editor_hides_suspected_secrets_and_rejects_saving_them(tmp_path):
    local, templates, _target = _protocol_fixture(tmp_path)
    from sync_core.application.service import ApplicationService
    from sync_core.config import SHARED_RULE_TOPICS

    store = tmp_path / "store"
    common = store / "common"
    common.mkdir(parents=True)
    for topic in SHARED_RULE_TOPICS:
        (common / f"{topic}.md").write_text(f"# {topic}\n", encoding="utf-8")
    target = common / "security.md"
    sample = "api_key = '" + "example-secret-value-12345" + "'\n"
    target.write_text(sample, encoding="utf-8")
    raw = json.loads(local.read_text(encoding="utf-8"))
    raw["config_repo"] = str(store)
    local.write_text(json.dumps(raw), encoding="utf-8")
    service = ApplicationService(local, template_root=templates)

    report = service.rule_library().data
    security = next(row for row in report["rules"] if row["topic"] == "security")
    assert security["status"] == "blocked_secret"
    assert security["content"] == ""

    import pytest
    with pytest.raises(ValueError, match="凭据"):
        service.save_rule(topic="security", content=sample)


def test_protocol_schema_operation_allowlist_matches_runtime():
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "schemas" / "desktop-rpc.schema.json").read_text(encoding="utf-8"))
    preview = schema["$defs"]["previewRequest"]
    operation_enum = preview["allOf"][1]["properties"]["operation"]["enum"]
    operation_conditions = {
        row["if"]["properties"]["operation"]["const"]
        for row in preview["allOf"]
        if "if" in row
    }

    assert set(operation_enum) == set(PARAMETERS)
    assert operation_conditions == set(PARAMETERS)


def test_preview_plan_rejects_stale_device_config_before_writing(tmp_path):
    local, templates, target = _protocol_fixture(tmp_path)
    protocol = ApplicationProtocol(local, template_root=templates)

    preview = protocol.handle({
        "protocol_version": 1,
        "request_id": "preview-1",
        "type": "preview",
        "operation": "rules",
    })
    assert preview["status"] == "preview"
    assert preview["can_apply"] is True
    assert preview["content_version"]
    assert not target.exists()

    config = json.loads(local.read_text(encoding="utf-8"))
    config["tool_versions"] = {"codex": "changed-after-preview"}
    local.write_text(json.dumps(config), encoding="utf-8")
    stale = protocol.handle({
        "protocol_version": 1,
        "request_id": "apply-stale",
        "type": "apply",
        "plan_id": preview["plan_id"],
    })
    assert stale["error"]["code"] == "E_PLAN_STALE"
    assert not target.exists()

    current = protocol.handle({
        "protocol_version": 1,
        "request_id": "preview-2",
        "type": "preview",
        "operation": "rules",
    })
    applied = protocol.handle({
        "protocol_version": 1,
        "request_id": "apply-current",
        "type": "apply",
        "plan_id": current["plan_id"],
    })
    assert applied["status"] == "applied"
    assert target.is_file()


def test_protocol_marks_informational_flows_read_only_until_user_selection(tmp_path):
    class FlowService:
        def verify_load(self, *, answer, **_kwargs):
            return ApplicationResult(data={"status": "instructions" if answer is None else "passed"})

        def diff(self, *, choice, **_kwargs):
            return ApplicationResult(data={"ready": choice is not None})

        def _raw_config(self):
            return {}

    protocol = ApplicationProtocol(tmp_path / "device.json", service_factory=lambda _path, _root: FlowService())

    instructions = protocol.handle({
        "protocol_version": 1,
        "request_id": "instructions",
        "type": "preview",
        "operation": "verify_load",
        "params": {"agent_id": "codex-main"},
    })
    answered = protocol.handle({
        "protocol_version": 1,
        "request_id": "answered",
        "type": "preview",
        "operation": "verify_load",
        "params": {"agent_id": "codex-main", "answer": "version", "record": True},
    })
    no_choice = protocol.handle({
        "protocol_version": 1,
        "request_id": "no-choice",
        "type": "preview",
        "operation": "diff",
    })

    assert instructions["can_apply"] is False
    assert "plan_id" not in instructions
    assert answered["can_apply"] is True
    assert no_choice["can_apply"] is False


def test_cancel_is_rejected_after_a_job_crosses_its_write_boundary():
    queued = JobControl()
    assert queued.request_cancel() == "accepted"

    writing = JobControl()
    writing.checkpoint(entering_write=True)
    assert writing.request_cancel() == "too_late"


def test_json_lines_jobs_are_serialized_and_stream_progress(tmp_path):
    counts = {"active": 0, "maximum": 0}
    lock = threading.Lock()

    class SlowService:
        def status(self):
            with lock:
                counts["active"] += 1
                counts["maximum"] = max(counts["maximum"], counts["active"])
            time.sleep(0.02)
            with lock:
                counts["active"] -= 1
            return ApplicationResult(data={"status": "ok"})

        def _raw_config(self):
            return {}

    protocol = ApplicationProtocol(tmp_path / "device.json", service_factory=lambda _path, _root: SlowService())
    requests = [
        {"protocol_version": 1, "request_id": f"read-{index}", "type": "preview", "operation": "status"}
        for index in (1, 2)
    ]
    output = io.StringIO()
    protocol.serve(io.StringIO("".join(json.dumps(row) + "\n" for row in requests)), output)
    events = [json.loads(line) for line in output.getvalue().splitlines()]

    assert counts["maximum"] == 1
    assert sum(event["type"] == "accepted" for event in events) == 2
    assert sum(event.get("stage") == "planning" for event in events) == 2
    assert sum(event.get("status") == "preview" for event in events) == 2


def test_json_lines_cancel_stops_a_queued_job_before_its_preview_or_write(tmp_path):
    first_started = threading.Event()
    release_first = threading.Event()
    second_preview_calls = 0

    class BlockingService:
        def status(self):
            first_started.set()
            assert release_first.wait(timeout=2)
            return ApplicationResult(data={"status": "ok"})

        def plan(self, *, mode):
            nonlocal second_preview_calls
            second_preview_calls += 1
            raise AssertionError(f"queued job should be cancelled before planning: {mode}")

        def _raw_config(self):
            return {}

    class EventStream(io.StringIO):
        def __init__(self):
            super().__init__()
            self.cancel_seen = threading.Event()

        def write(self, value):
            result = super().write(value)
            if '"type":"cancel_result"' in value:
                self.cancel_seen.set()
            return result

    protocol = ApplicationProtocol(
        tmp_path / "device.json",
        service_factory=lambda _path, _root: BlockingService(),
    )
    output = EventStream()

    # Read the generated job id from the accepted event before sending cancel.
    initial = [
        {"protocol_version": 1, "request_id": "slow", "type": "preview", "operation": "status"},
        {"protocol_version": 1, "request_id": "queued", "type": "preview", "operation": "rules"},
    ]
    initial_input = "".join(json.dumps(row) + "\n" for row in initial)

    class ChainedInput:
        def __iter__(self):
            yield from initial_input.splitlines(keepends=True)
            assert first_started.wait(timeout=2)
            # Wait until both jobs have been accepted, then cancel the queued one.
            deadline = time.monotonic() + 2
            while output.getvalue().count('"type":"accepted"') < 2 and time.monotonic() < deadline:
                time.sleep(0.001)
            assert output.getvalue().count('"type":"accepted"') == 2
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            queued_job = next(event["job_id"] for event in events if event.get("request_id") == "queued" and event["type"] == "accepted")
            yield json.dumps({
                "protocol_version": 1,
                "request_id": "cancel-queued",
                "type": "cancel",
                "job_id": queued_job,
            }) + "\n"
            assert output.cancel_seen.wait(timeout=2)
            release_first.set()

    worker = threading.Thread(target=protocol.serve, args=(ChainedInput(), output))
    worker.start()
    try:
        worker.join(timeout=3)
    finally:
        release_first.set()
        worker.join(timeout=1)
    assert not worker.is_alive()
    events = [json.loads(line) for line in output.getvalue().splitlines()]

    assert second_preview_calls == 0
    assert next(event for event in events if event["type"] == "cancel_result")["status"] == "accepted"
    assert next(event for event in events if event.get("request_id") == "queued" and event["type"] == "result")["status"] == "cancelled"


def test_json_lines_shutdown_acknowledges_and_stops_accepting_requests(tmp_path):
    import io
    import json

    incoming = io.StringIO(
        json.dumps({"protocol_version": 1, "request_id": "close", "type": "shutdown"})
        + "\n"
        + json.dumps({"protocol_version": 1, "request_id": "after-close", "type": "preview", "operation": "status"})
        + "\n"
    )
    outgoing = io.StringIO()

    ApplicationProtocol(tmp_path / "device.json").serve(incoming, outgoing)

    events = [json.loads(line) for line in outgoing.getvalue().splitlines()]
    assert events == [{
        "protocol_version": 1,
        "request_id": "close",
        "type": "shutdown_accepted",
    }]


def test_status_preview_reports_missing_device_config_without_writing(tmp_path):
    device_config = tmp_path / "user-data" / "device.json"
    response = ApplicationProtocol(device_config).handle({
        "protocol_version": 1,
        "request_id": "first-run-status",
        "type": "preview",
        "operation": "status",
    })

    assert response["status"] == "preview"
    assert response["can_apply"] is False
    assert response["result"] == {
        "status": "not_configured",
        "configured": False,
        "state": None,
        "receipts": [],
        "next_step": "首次设置",
    }
    assert not device_config.exists()


def test_desktop_rpc_child_exits_cleanly_after_shutdown_request(tmp_path):
    root = Path(__file__).resolve().parents[1]
    requests = [
        {"protocol_version": 1, "request_id": "bad", "type": "preview", "operation": "unknown"},
        {"protocol_version": 1, "request_id": "close", "type": "shutdown"},
        {"protocol_version": 1, "request_id": "ignored", "type": "preview", "operation": "status"},
    ]
    process = subprocess.Popen(
        [sys.executable, str(root / "scripts" / "desktop_rpc.py"), "--local", str(tmp_path / "device.json")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=root,
    )
    stdout, stderr = process.communicate("\n".join(json.dumps(item) for item in requests) + "\n", timeout=5)
    events = [json.loads(line) for line in stdout.splitlines()]

    assert process.returncode == 0, stderr
    assert [event["request_id"] for event in events] == ["bad", "close"]
    assert events[-1]["type"] == "shutdown_accepted"


def test_json_lines_preserves_request_id_for_rejected_request(tmp_path):
    protocol = ApplicationProtocol(tmp_path / "device.json")
    output = io.StringIO()
    protocol.serve(
        io.StringIO(json.dumps({
            "protocol_version": 1,
            "request_id": "bad-op",
            "type": "preview",
            "operation": "not-supported",
        }) + "\n"),
        output,
    )
    event = json.loads(output.getvalue())

    assert event["request_id"] == "bad-op"
    assert event["error"]["code"] == "E_OPERATION_UNKNOWN"


def test_invalid_json_does_not_reuse_a_previous_request_id(tmp_path):
    protocol = ApplicationProtocol(tmp_path / "device.json")
    requests = [
        json.dumps({
            "protocol_version": 1,
            "request_id": "first",
            "type": "preview",
            "operation": "not-supported",
        }),
        "{invalid json",
    ]
    output = io.StringIO()
    protocol.serve(io.StringIO("\n".join(requests) + "\n"), output)
    events = [json.loads(line) for line in output.getvalue().splitlines()]

    assert events[0]["request_id"] == "first"
    assert events[1]["request_id"] is None
    assert events[1]["error"]["code"] == "E_REQUEST_JSON"


def test_desktop_rpc_entrypoint_uses_utf8_json_lines_without_writing_preview(tmp_path):
    local, templates, _target = _protocol_fixture(tmp_path)
    source = tmp_path / "legacy-device.json"
    source.write_bytes(local.read_bytes())
    target = tmp_path / "user-data" / "device.json"
    request = {
        "protocol_version": 1,
        "request_id": "import-preview",
        "type": "preview",
        "operation": "import_config",
        "params": {"source": str(source)},
    }
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "desktop_rpc.py"),
            "--local",
            str(target),
            "--template-root",
            str(templates),
        ],
        input=json.dumps(request, ensure_ascii=False) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=root,
        check=False,
    )
    events = [json.loads(line) for line in result.stdout.splitlines()]

    assert result.returncode == 0, result.stderr
    assert events[0]["type"] == "accepted"
    assert events[-1]["status"] == "preview"
    assert events[-1]["result"]["written"] is False
    assert not target.exists()


def test_dt12_apply_requires_explicit_inventory_memory_and_handoff_choices():
    can_apply = ApplicationProtocol._can_apply

    assert not can_apply("inventory", {}, {"ready": True})
    assert can_apply("inventory", {"save": True}, {"ready": True})
    assert not can_apply("memory_setup", {}, {"selection_preview": {"status": "ready"}})
    assert not can_apply("memory_setup", {"selections": [{"id": "demo", "path": "/memory"}]}, {"selection_preview": {"status": "blocked"}})
    assert can_apply("memory_setup", {"selections": [{"id": "demo", "path": "/memory"}]}, {"selection_preview": {"status": "ready"}})
    assert not can_apply("start", {}, {"ready": False})
    assert can_apply("start", {}, {"ready": True})
    assert not can_apply("finish", {"handoff_text": "incomplete"}, {"handoff_missing_fields": ["tests"]})
    assert can_apply("finish", {"handoff_text": "complete"}, {"handoff_missing_fields": []})
    assert not can_apply("project_setup", {}, {"ready": False})
    assert can_apply("project_setup", {}, {"ready": True})


def test_dt12_project_setup_is_previewed_then_saved_with_backup(tmp_path):
    local, templates, _target = _protocol_fixture(tmp_path)
    project = tmp_path / "project-source"
    project.mkdir()
    protocol = ApplicationProtocol(local, template_root=templates)

    preview = protocol.handle({
        "protocol_version": 1,
        "request_id": "project-preview",
        "type": "preview",
        "operation": "project_setup",
        "params": {"project_id": "demo", "path": str(project)},
    })
    assert preview["status"] == "preview"
    assert preview["can_apply"] is True
    assert "projects" not in json.loads(local.read_text(encoding="utf-8"))

    applied = protocol.handle({
        "protocol_version": 1,
        "request_id": "project-apply",
        "type": "apply",
        "plan_id": preview["plan_id"],
    })
    assert applied["status"] == "applied"
    assert applied["result"]["written"] is True
    assert Path(applied["result"]["backup"]).is_dir()
    assert json.loads(local.read_text(encoding="utf-8"))["projects"]["demo"] == str(project.resolve())


def test_dt12_snapshot_inventory_returns_metadata_and_handles_bad_receipt(tmp_path):
    from sync_core.application.service import ApplicationService
    from sync_core.snapshots import create_snapshot

    local, templates, _target = _protocol_fixture(tmp_path)
    memory_root = tmp_path / "memory-repo"
    manifest = create_snapshot(
        memory_root,
        device="windows-a",
        scope="demo",
        tool="codex",
        project_id="demo",
        files={"MEMORY.md": b"private body is never returned"},
    )
    receipt = memory_root / "confirmations" / "windows-a" / f"{manifest['snapshot_id']}.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("not json", encoding="utf-8")

    report = ApplicationService(local, template_root=templates).snapshots().data
    row = next(item for item in report["snapshots"] if item["snapshot_id"] == manifest["snapshot_id"])
    assert row["status"] == "valid"
    assert row["confirmed"] is False
    assert row["restorable"] is False
    assert row["file_count"] == 1
    assert "files" not in row


def test_dt12_selected_memory_source_changes_invalidate_preview_version(tmp_path):
    from sync_core.application.service import ApplicationService

    local, templates, _target = _protocol_fixture(tmp_path)
    source = tmp_path / "memory-source"
    source.mkdir()
    memory_file = source / "MEMORY.md"
    memory_file.write_text("first version", encoding="utf-8")
    protocol = ApplicationProtocol(local, template_root=templates)
    params = {"selections": [{"id": "demo", "path": str(source)}]}
    result = ApplicationService(local, template_root=templates).memory_setup(selections=params["selections"])

    before = protocol._version("memory_setup", params, result)
    memory_file.write_text("changed after preview", encoding="utf-8")
    after = protocol._version("memory_setup", params, result)

    assert before != after
