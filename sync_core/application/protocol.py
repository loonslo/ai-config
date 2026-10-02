"""Versioned JSON-lines interface between a desktop shell and local services."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, is_dataclass
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, IO, Mapping
import uuid

from .service import ApplicationResult, ApplicationService
from ..transaction import PlannedChanges

PROTOCOL_VERSION = 1
PLAN_TTL_SECONDS = 20 * 60

PARAMETERS: dict[str, frozenset[str]] = {
    "import_config": frozenset({"source"}),
    "package_import": frozenset({"package_path", "decisions", "manual_values", "selections", "apply_to_agents"}),
    "package_export": frozenset({"destination", "format", "selected_sources", "extension_kinds"}),
    "package_capabilities": frozenset(),
    "extension_capture": frozenset({"kind", "profile", "name", "source"}),
    "cloud": frozenset({"server", "action", "options"}),
    "portable_restore": frozenset({"project_id", "profile"}),
    "portable_project": frozenset({"project_id", "profile", "handoff_id"}),
    "git_transport": frozenset({"action"}),
    "setup": frozenset({"store_path", "remote", "state_dir", "memory_repo", "tools", "tool_roots"}),
    "rule_library": frozenset(),
    "save_rule": frozenset({"topic", "content"}),
    "quick": frozenset(),
    "rules": frozenset(),
    "config": frozenset(),
    "memory": frozenset(),
    "scan": frozenset({"save"}),
    "migrate": frozenset({"item", "choice"}),
    "declare": frozenset({"agent_id", "root", "entry", "entry_mode", "profile"}),
    "sync": frozenset({"fetch", "publish"}),
    "status": frozenset(),
    "diff": frozenset({"choice"}),
    "detach": frozenset({"agent_id", "restore_original"}),
    "verify_load": frozenset({"agent_id", "answer", "record"}),
    "undo": frozenset({"list_only", "operation_id", "index"}),
    "doctor": frozenset({"recover"}),
    "inventory": frozenset({"save"}),
    "snapshots": frozenset(),
    "memory_setup": frozenset({"disable", "selections"}),
    "project": frozenset({"project_id", "handoff_id"}),
    "project_setup": frozenset({"project_id", "path"}),
    "restore_snapshot": frozenset({"snapshot_id"}),
    "start": frozenset({"project_id", "handoff_id"}),
    "finish": frozenset({"project_id", "handoff_file", "handoff_text"}),
}
READ_ONLY = frozenset({"status", "project", "rule_library", "snapshots", "package_capabilities", "portable_project"})
REQUIRED_PARAMS: dict[str, frozenset[str]] = {
    "import_config": frozenset({"source"}),
    "package_import": frozenset({"package_path"}),
    "package_export": frozenset({"destination", "format"}),
    "extension_capture": frozenset({"kind", "profile", "name", "source"}),
    "cloud": frozenset({"server", "action"}),
    "portable_restore": frozenset({"project_id", "profile"}),
    "portable_project": frozenset({"project_id", "profile"}),
    "git_transport": frozenset({"action"}),
    "save_rule": frozenset({"topic", "content"}),
    "declare": frozenset({"agent_id", "root"}),
    "detach": frozenset({"agent_id"}),
    "verify_load": frozenset({"agent_id"}),
    "restore_snapshot": frozenset({"snapshot_id"}),
    "start": frozenset({"project_id", "handoff_id"}),
    "finish": frozenset({"project_id"}),
}
STRING_PARAMS = frozenset({
    "server", "action", "kind", "name", "source", "package_path", "destination", "format", "store_path", "remote", "state_dir", "memory_repo", "topic", "item", "choice", "agent_id",
    "root", "entry", "entry_mode", "profile", "answer", "operation_id", "project_id", "handoff_id",
    "snapshot_id", "handoff_file", "handoff_text", "path",
})
BOOLEAN_PARAMS = frozenset({"fetch", "publish", "restore_original", "record", "list_only", "recover", "disable", "save", "apply_to_agents"})


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _Cancelled(BaseException):
    pass


class JobControl:
    """Cancellation is accepted only before a task crosses its write boundary."""

    def __init__(self) -> None:
        self.job_id = uuid.uuid4().hex
        self.cancel_requested = threading.Event()
        self.safe_to_cancel = True
        self.finished = False
        self.lock = threading.Lock()

    def request_cancel(self) -> str:
        with self.lock:
            if self.finished:
                return "already_finished"
            if not self.safe_to_cancel:
                return "too_late"
            self.cancel_requested.set()
            return "accepted"

    def checkpoint(self, *, entering_write: bool = False) -> None:
        with self.lock:
            if self.cancel_requested.is_set():
                raise _Cancelled
            if entering_write:
                self.safe_to_cancel = False


class ApplicationProtocol:
    """Validate desktop requests, retain previews, and recheck them before apply."""

    def __init__(
        self,
        local_path: Path,
        *,
        template_root: Path | None = None,
        service_factory: Callable[[Path, Path | None], ApplicationService] | None = None,
    ) -> None:
        self.local_path = Path(local_path)
        self.template_root = Path(template_root) if template_root is not None else None
        self._service_factory = service_factory or (
            lambda path, root: ApplicationService(path, template_root=root)
        )
        self._plans: dict[str, dict[str, Any]] = {}
        self._plans_lock = threading.Lock()

    def _service(self) -> ApplicationService:
        return self._service_factory(self.local_path, self.template_root)

    @staticmethod
    def validate_request(request: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
        if not isinstance(request, Mapping):
            raise ProtocolError("E_REQUEST_INVALID", "Request must be a JSON object.")
        version = request.get("protocol_version")
        if not isinstance(version, int) or isinstance(version, bool) or version != PROTOCOL_VERSION:
            raise ProtocolError("E_PROTOCOL_VERSION", f"Unsupported protocol version: {request.get('protocol_version')!r}.")
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 128:
            raise ProtocolError("E_REQUEST_ID", "request_id must be a non-empty string of at most 128 characters.")
        kind = request.get("type")
        if kind not in {"preview", "apply", "cancel", "shutdown"}:
            raise ProtocolError("E_REQUEST_TYPE", "type must be preview, apply, or cancel.")
        if kind == "shutdown":
            return kind, None, {}
        if kind == "preview":
            operation = request.get("operation")
            if not isinstance(operation, str) or operation not in PARAMETERS:
                raise ProtocolError("E_OPERATION_UNKNOWN", f"Unsupported operation: {operation!r}.")
            params = request.get("params", {})
            if not isinstance(params, dict):
                raise ProtocolError("E_PARAMS_INVALID", "params must be an object.")
            extra = set(params) - PARAMETERS[operation]
            if extra:
                raise ProtocolError("E_PARAMS_UNKNOWN", "Unsupported parameter(s): " + ", ".join(sorted(extra)) + ".")
            missing = REQUIRED_PARAMS.get(operation, frozenset()) - set(params)
            if operation == "finish" and not ({"handoff_file", "handoff_text"} & set(params)):
                missing = missing | {"handoff_file or handoff_text"}
            if missing:
                raise ProtocolError("E_PARAMS_REQUIRED", "Missing required parameter(s): " + ", ".join(sorted(missing)) + ".")
            if operation == "finish" and {"handoff_file", "handoff_text"}.issubset(params):
                raise ProtocolError("E_PARAMS_INVALID", "Provide only one of handoff_file or handoff_text.")
            if operation == "cloud":
                cloud_fields = {
                    "login": {"issuer", "client_id", "audience"}, "poll_login": set(), "logout": set(),
                    "spaces": set(), "create_space": {"name"}, "generate_key": {"space"},
                    "unlock": {"space", "material"}, "versions": {"space"},
                    "upload": {"space", "package_path", "expected_head"},
                    "download": {"space", "version", "destination"}, "devices": set(),
                    "revoke": {"device"}, "receipt": {"summary"},
                }
                action = params.get("action")
                options = params.get("options", {})
                if not isinstance(action, str) or action not in cloud_fields or not isinstance(options, dict) or set(options) != cloud_fields[action]:
                    raise ProtocolError("E_PARAMS_INVALID", "Invalid cloud action or options.")
                if any(not isinstance(value, str) or not value or len(value) > 4096 for key, value in options.items() if key != "summary"):
                    raise ProtocolError("E_PARAMS_INVALID", "Cloud options must be bounded strings.")
                if action == "receipt" and (not isinstance(options["summary"], dict) or set(options["summary"]) != {"space_id", "version_id", "content_id", "state", "load_verified"}):
                    raise ProtocolError("E_PARAMS_INVALID", "Invalid receipt summary.")
                import re
                for key in {"space", "version", "device"} & options.keys():
                    if not re.fullmatch(r"[a-f0-9]{32}", options[key]):
                        raise ProtocolError("E_PARAMS_INVALID", "Invalid cloud resource ID.")
                if action == "upload" and options["expected_head"] != "none" and not re.fullmatch(r"[a-f0-9]{32}", options["expected_head"]):
                    raise ProtocolError("E_PARAMS_INVALID", "Invalid cloud parent version.")
            for name, item in params.items():
                if name == "extension_kinds" and (not isinstance(item, list) or len(set(item)) != len(item) or any(kind not in {"skills", "mcp", "memory", "handoffs"} for kind in item)):
                    raise ProtocolError("E_PARAMS_INVALID", "Invalid extension scope.")
                if name in STRING_PARAMS and (not isinstance(item, str) or not item):
                    raise ProtocolError("E_PARAMS_INVALID", f"{name} must be a non-empty string.")
                if name in BOOLEAN_PARAMS and not isinstance(item, bool):
                    raise ProtocolError("E_PARAMS_INVALID", f"{name} must be a boolean.")
                if name == "index" and (not isinstance(item, int) or isinstance(item, bool) or item < 1):
                    raise ProtocolError("E_PARAMS_INVALID", "index must be a positive integer.")
                if name == "tools" and (not isinstance(item, list) or any(not isinstance(tool, str) for tool in item)):
                    raise ProtocolError("E_PARAMS_INVALID", "tools must be an array of strings.")
                if name == "selected_sources" and (
                    operation != "package_export"
                    or not isinstance(item, list)
                    or len(item) > 1024
                    or any(not isinstance(source, str) or not source or len(source) > 4096 for source in item)
                    or len(set(item)) != len(item)
                ):
                    raise ProtocolError("E_PARAMS_INVALID", "selected_sources must be a unique array of portable source identifiers.")
                if name == "tool_roots" and (
                    not isinstance(item, dict)
                    or any(
                        not isinstance(tool, str)
                        or not isinstance(root, str)
                        or not root
                        or not Path(root).expanduser().is_absolute()
                        for tool, root in item.items()
                    )
                ):
                    raise ProtocolError("E_PARAMS_INVALID", "tool_roots must map agent names to absolute paths.")
                if name == "store_path" and not Path(item).expanduser().is_absolute():
                    raise ProtocolError("E_PARAMS_INVALID", "store_path must be an absolute path.")
                if name == "package_path" and not Path(item).expanduser().is_absolute():
                    raise ProtocolError("E_PARAMS_INVALID", "package_path must be an absolute path.")
                if name == "destination" and not Path(item).expanduser().is_absolute():
                    raise ProtocolError("E_PARAMS_INVALID", "destination must be an absolute path.")
                if operation == "package_export" and name == "format" and item not in {"archive", "directory"}:
                    raise ProtocolError("E_PARAMS_INVALID", "format must be archive or directory.")
                if name == "root" and not Path(item).expanduser().is_absolute():
                    raise ProtocolError("E_PARAMS_INVALID", "root must be an absolute path.")
                if name == "path" and not Path(item).expanduser().is_absolute():
                    raise ProtocolError("E_PARAMS_INVALID", "path must be an absolute path.")
                if name == "content" and (
                    not isinstance(item, str)
                    or "\x00" in item
                    or len(item.encode("utf-8")) > 262144
                ):
                    raise ProtocolError("E_PARAMS_INVALID", "content must be UTF-8 text no larger than 256 KiB.")
                if name == "handoff_text" and (
                    not isinstance(item, str)
                    or "\x00" in item
                    or len(item.encode("utf-8")) > 131072
                ):
                    raise ProtocolError("E_PARAMS_INVALID", "handoff_text must be UTF-8 text no larger than 128 KiB.")
                if name == "selections" and (not isinstance(item, list) or any(not isinstance(row, dict) for row in item)):
                    if operation != "package_import":
                        raise ProtocolError("E_PARAMS_INVALID", "selections must be an array of objects.")
                if operation == "package_import" and name == "decisions" and (
                    not isinstance(item, dict)
                    or len(item) > 1024
                    or any(
                        not isinstance(key, str)
                        or not key
                        or len(key) > 2048
                        or value not in {"keep_local", "use_package", "manual_merge"}
                        for key, value in item.items()
                    )
                ):
                    raise ProtocolError("E_PARAMS_INVALID", "decisions must map supported conflict keys to explicit choices.")
                if operation == "package_import" and name == "manual_values" and (
                    not isinstance(item, dict)
                    or len(item) > 256
                    or any(
                        not isinstance(key, str)
                        or len(key) > 2048
                        or not isinstance(value, str)
                        or "\x00" in value
                        or len(value.encode("utf-8")) > 262144
                        for key, value in item.items()
                    )
                ):
                    raise ProtocolError("E_PARAMS_INVALID", "manual_values must contain UTF-8 rule text up to 256 KiB per entry.")
                if operation == "package_import" and name == "selections" and (
                    not isinstance(item, dict)
                    or len(item) > 256
                    or any(
                        not isinstance(key, str) or not key or len(key) > 128
                        or not isinstance(value, str) or not value or len(value) > 128
                        for key, value in item.items()
                    )
                ):
                    raise ProtocolError("E_PARAMS_INVALID", "selections must map choice keys to offered instance ids.")
            return kind, operation, dict(params)
        if kind == "apply":
            plan_id = request.get("plan_id")
            if not isinstance(plan_id, str) or not plan_id:
                raise ProtocolError("E_PLAN_ID", "apply requires a plan_id.")
            return kind, plan_id, {}
        job_id = request.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise ProtocolError("E_JOB_ID", "cancel requires a job_id.")
        return kind, job_id, {}

    def handle(
        self,
        request: Mapping[str, Any],
        *,
        control: JobControl | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        request_id = request.get("request_id") if isinstance(request, Mapping) else None
        try:
            kind, value, params = self.validate_request(request)
            if kind == "cancel":
                raise ProtocolError("E_CANCEL_CHANNEL", "Cancellation is available only while the JSON-lines service is running.")
            if kind == "shutdown":
                raise ProtocolError("E_SHUTDOWN_CHANNEL", "Shutdown is available only while the JSON-lines service is running.")
            if kind == "preview":
                return self._preview(request_id, value, params, control=control, progress=progress)
            return self._apply(request_id, value, control=control, progress=progress)
        except _Cancelled:
            return self._response(request_id, "cancelled", error={"code": "E_CANCELLED", "message": "Operation cancelled before its write boundary."})
        except ProtocolError as error:
            return self._response(request_id, "failed", error={"code": error.code, "message": str(error)})
        except Exception as error:  # noqa: BLE001 - protocol boundary returns structured errors, not tracebacks
            code = getattr(error, "code", None) or "E_OPERATION_FAILED"
            return self._response(request_id, "failed", error={"code": str(code), "message": str(error)})

    @staticmethod
    def _response(request_id: Any, status: str, **values: Any) -> dict[str, Any]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "type": "result",
            "status": status,
            **values,
        }

    def _preview(
        self,
        request_id: Any,
        operation: str,
        params: dict[str, Any],
        *,
        control: JobControl | None,
        progress: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        if control:
            control.checkpoint()
        if progress:
            progress("planning")
        result = self._invoke(operation, params, apply=False, progress=progress)
        if operation == "setup" and self.local_path.exists():
            result = ApplicationResult(
                data={
                    **result.data,
                    "ready": False,
                    "status": "already_configured",
                    "reason": "本机设备配置已存在；首次设置不会覆盖它。请改用现有配置维护流程。",
                },
                detail=result.detail,
            )
        version = self._version(operation, params, result)
        applyable = self._can_apply(operation, params, result.data)
        plan_id = uuid.uuid4().hex if applyable else None
        if plan_id:
            with self._plans_lock:
                self._expire_plans()
                self._plans[plan_id] = {
                    "operation": operation,
                    "params": params,
                    "version": version,
                    "expires": time.monotonic() + PLAN_TTL_SECONDS,
                }
        payload: dict[str, Any] = {
            "operation": operation,
            "can_apply": applyable,
            "content_version": version,
            "result": result.data,
        }
        if plan_id:
            payload["plan_id"] = plan_id
            payload["expires_in_seconds"] = PLAN_TTL_SECONDS
        if control:
            try:
                control.checkpoint()
            except _Cancelled:
                if plan_id:
                    with self._plans_lock:
                        self._plans.pop(plan_id, None)
                raise
        return self._response(request_id, "preview", **payload)

    def _apply(
        self,
        request_id: Any,
        plan_id: str,
        *,
        control: JobControl | None,
        progress: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        with self._plans_lock:
            self._expire_plans()
            plan = self._plans.pop(plan_id, None)
        if plan is None:
            raise ProtocolError("E_PLAN_UNKNOWN", "Plan is missing, expired, or already used; create a new preview.")
        if plan["operation"] in READ_ONLY or (plan["operation"] == "undo" and plan["params"].get("list_only")):
            raise ProtocolError("E_PLAN_READ_ONLY", "This preview does not support apply.")
        if progress:
            progress("rechecking_preview")
        current = self._invoke(plan["operation"], plan["params"], apply=False, progress=progress)
        current_version = self._version(plan["operation"], plan["params"], current)
        if current_version != plan["version"]:
            raise ProtocolError("E_PLAN_STALE", "Local inputs changed after preview. Create a new preview before applying.")
        if control:
            control.checkpoint()
        if progress:
            progress("applying")

        def checkpoint(stage: str) -> None:
            if control:
                external_write = (stage == "fetch" and plan["params"].get("fetch")) or (
                    stage == "publish" and plan["params"].get("publish")
                )
                local_write = stage in {"apply", "verify", "receipt"}
                control.checkpoint(entering_write=bool(external_write or local_write))
            if progress:
                progress(stage)

        if control and plan["operation"] != "sync":
            control.checkpoint(entering_write=True)
        result = self._invoke(plan["operation"], plan["params"], apply=True, progress=checkpoint)
        return self._response(
            request_id,
            "applied",
            operation=plan["operation"],
            content_version=current_version,
            result=result.data,
        )

    @staticmethod
    def _can_apply(operation: str, params: Mapping[str, Any], result: Mapping[str, Any]) -> bool:
        if operation in READ_ONLY:
            return False
        if operation == "setup":
            return bool(result.get("ready"))
        if operation == "save_rule":
            return bool(result.get("ready"))
        if operation == "package_import":
            return result.get("can_apply") is True
        if operation == "package_export":
            return result.get("can_apply") is True
        if operation in {"extension_capture", "cloud", "portable_restore", "git_transport"}:
            return result.get("can_apply") is True
        if operation == "migrate":
            return bool(params.get("item") and params.get("choice"))
        if operation == "scan":
            return bool(params.get("save"))
        if operation == "diff":
            return bool(params.get("choice")) and bool(result.get("ready"))
        if operation == "verify_load":
            return bool(params.get("answer")) and params.get("record", True) is True
        if operation == "doctor":
            return bool(params.get("recover"))
        if operation == "undo":
            return not params.get("list_only") and bool(params.get("operation_id") or params.get("index"))
        if operation == "inventory":
            return bool(params.get("save"))
        if operation == "memory_setup":
            if params.get("disable"):
                return True
            preview = result.get("selection_preview")
            return bool(params.get("selections")) and isinstance(preview, Mapping) and preview.get("status") == "ready"
        if operation == "start":
            return bool(result.get("ready"))
        if operation == "finish":
            return bool(params.get("handoff_file") or params.get("handoff_text")) and not result.get("handoff_missing_fields")
        if operation == "project_setup":
            return bool(result.get("ready"))
        return True

    def _invoke(
        self,
        operation: str,
        params: Mapping[str, Any],
        *,
        apply: bool,
        progress: Callable[[str], None] | None,
    ) -> ApplicationResult:
        service = self._service()
        if operation == "package_capabilities":
            return service.package_capabilities()
        if operation == "cloud":
            return service.cloud(server=params["server"], action=params["action"], options=params.get("options"), apply=apply)
        if operation == "portable_restore":
            return service.portable_restore(project_id=params["project_id"], profile=params["profile"], apply=apply)
        if operation == "git_transport":
            return service.git_transport(action=params["action"], apply=apply)
        if operation == "extension_capture":
            return service.extension_capture(kind=params["kind"], profile=params["profile"], name=params["name"], source=Path(params["source"]), apply=apply)
        if operation == "rule_library":
            return service.rule_library()
        if operation == "save_rule":
            return service.save_rule(topic=str(params["topic"]), content=str(params["content"]), apply=apply)
        if operation in {"rules", "config", "memory"}:
            plan = service.plan(mode=operation)
            summary = {
                "status": "preview",
                "changes": [
                    {"path": str(path), "action": "delete" if data is None else "write", "size": len(data) if data is not None else 0}
                    for path, data in plan.items()
                ],
                "count": len(plan),
            }
            if apply:
                applied = service.apply_plan(plan)
                return ApplicationResult(data=applied, detail=plan)
            return ApplicationResult(data=summary, detail=plan)
        if operation == "import_config":
            return service.import_config(source=Path(params["source"]), apply=apply)
        if operation == "package_import":
            return service.package_import(
                package_path=Path(params["package_path"]),
                decisions=params.get("decisions"),
                manual_values=params.get("manual_values"),
                selections=params.get("selections"),
                apply_to_agents=params.get("apply_to_agents", True),
                apply=apply,
            )
        if operation == "package_export":
            return service.package_export(
                destination=Path(params["destination"]),
                format=str(params["format"]),
                selected_sources=params.get("selected_sources"),
                extension_kinds=params.get("extension_kinds"),
                apply=apply,
            )
        if operation == "setup":
            from ..layout import default_store_path

            return service.setup(
                store_path=Path(params["store_path"]) if params.get("store_path") else default_store_path(),
                remote=params.get("remote"),
                state_dir=Path(params["state_dir"]) if params.get("state_dir") else None,
                memory_repo=Path(params["memory_repo"]) if params.get("memory_repo") else None,
                tools=params.get("tools"),
                tool_roots=params.get("tool_roots"),
                apply=apply,
            )
        if operation == "quick":
            return service.quick_setup(apply=apply)
        if operation == "scan":
            return service.scan(save=apply and bool(params.get("save")))
        if operation == "migrate":
            return service.migrate(item=params.get("item"), choice=params.get("choice"), apply=apply)
        if operation == "declare":
            return service.declare(
                agent_id=str(params["agent_id"]),
                root=str(params["root"]),
                entry=params.get("entry"),
                entry_mode=params.get("entry_mode"),
                profile=params.get("profile"),
                apply=apply,
            )
        if operation == "sync":
            if not apply and (params.get("fetch") or params.get("publish")):
                raise ProtocolError(
                    "E_PREVIEW_SIDE_EFFECT",
                    "fetch/publish can change the shared checkout or remote; preview locally first without these options.",
                )
            return service.sync(
                apply=apply,
                fetch=bool(params.get("fetch")),
                publish=bool(params.get("publish")),
                checkpoint=progress,
            )
        if operation == "status":
            return service.status()
        if operation == "diff":
            result = service.diff(choice=params.get("choice"), apply=apply)
            outcomes = result.data.get("outcomes", [])
            safe_outcomes = [
                {key: value for key, value in outcome.items() if key != "value"}
                for outcome in outcomes
                if isinstance(outcome, Mapping)
            ]
            return ApplicationResult(data={**result.data, "outcomes": safe_outcomes}, detail=result.detail)
        if operation == "detach":
            return service.detach(
                agent_id=str(params["agent_id"]),
                restore_original=bool(params.get("restore_original")),
                apply=apply,
            )
        if operation == "verify_load":
            return service.verify_load(
                agent_id=str(params["agent_id"]),
                answer=params.get("answer"),
                record=apply and bool(params.get("record", True)),
            )
        if operation == "undo":
            return service.undo(
                list_only=bool(params.get("list_only")),
                operation_id=params.get("operation_id"),
                index=params.get("index"),
                apply=apply,
            )
        if operation == "doctor":
            return service.doctor(recover=apply and bool(params.get("recover")))
        if operation == "inventory":
            return service.inventory(save=apply)
        if operation == "snapshots":
            return service.snapshots()
        if operation == "memory_setup":
            return service.memory_setup(
                disable=bool(params.get("disable")),
                apply=apply,
                selections=params.get("selections"),
            )
        if operation == "project":
            return service.project(project_id=params.get("project_id"), handoff_id=params.get("handoff_id"))
        if operation == "project_setup":
            return service.project_setup(project_id=str(params["project_id"]), path=Path(params["path"]), apply=apply)
        if operation == "restore_snapshot":
            return service.restore_snapshot(snapshot_id=str(params["snapshot_id"]), apply=apply)
        if operation == "start":
            return service.start(project_id=str(params["project_id"]), handoff_id=str(params["handoff_id"]), apply=apply)
        if operation == "finish":
            return service.finish(
                project_id=str(params["project_id"]),
                handoff_file=Path(params["handoff_file"]) if params.get("handoff_file") else None,
                handoff_text=params.get("handoff_text"),
                apply=apply,
            )
        raise ProtocolError("E_OPERATION_UNKNOWN", f"Unsupported operation: {operation}.")

    def _version(self, operation: str, params: Mapping[str, Any], result: ApplicationResult) -> str:
        """Hash plans and their read set without returning local content or paths as a token."""
        service = self._service()
        material: dict[str, Any] = {
            "operation": operation,
            "params": dict(params),
            "result": _stable(result.data),
            "detail": _stable(result.detail),
            "config": _file_version(self.local_path),
            "agent_targets": {},
            "memory_sources": {},
            "detail_path_versions": {str(path): _file_version(path) for path in _walk_paths(result.detail)},
        }
        if self.local_path.is_file():
            try:
                from ..agents import managed_targets
                from ..config import absolute, load
                from ..memory_io import stable_files

                raw = load(self.local_path).raw
                for _instance, target in managed_targets(raw):
                    material["agent_targets"][str(target.path)] = _file_version(target.path)
                if operation in {"memory", "memory_setup", "start", "finish"}:
                    for item in raw.get("memories", []):
                        source = absolute(item["path"])
                        material["memory_sources"][item["id"]] = {
                            name: hashlib.sha256(data).hexdigest()
                            for name, data in stable_files(source, item.get("exclude", [])).items()
                        }
                    if operation == "memory_setup":
                        for selection in params.get("selections", []):
                            if not isinstance(selection, Mapping):
                                continue
                            path = selection.get("path")
                            if isinstance(path, str) and path:
                                material["memory_sources"][f"selection:{path}"] = {
                                    name: hashlib.sha256(data).hexdigest()
                                    for name, data in stable_files(absolute(path)).items()
                                }
                    if operation == "start":
                        project_id = str(params.get("project_id", ""))
                        shared = absolute(raw["memory_repo"]) / "claude" / project_id
                        material["memory_sources"]["shared"] = {
                            name: hashlib.sha256(data).hexdigest()
                            for name, data in stable_files(shared).items()
                        }
                if operation == "finish" and params.get("handoff_file"):
                    material["handoff"] = _file_version(Path(str(params["handoff_file"])))
            except (OSError, ValueError):
                material["read_set_status"] = "changed_or_unavailable"
        encoded = json.dumps(_stable(material), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _expire_plans(self) -> None:
        now = time.monotonic()
        expired = [key for key, value in self._plans.items() if value["expires"] <= now]
        for key in expired:
            self._plans.pop(key, None)

    def serve(self, incoming: IO[str], outgoing: IO[str]) -> None:
        """Serve newline-delimited requests; workers serialize operations and stream progress."""
        output_lock = threading.Lock()
        jobs: dict[str, tuple[JobControl, str]] = {}
        jobs_lock = threading.Lock()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-config-operation")

        def emit(event: Mapping[str, Any]) -> None:
            with output_lock:
                outgoing.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                outgoing.flush()

        def run(request: dict[str, Any], control: JobControl) -> None:
            request_id = request.get("request_id")
            emit({"protocol_version": PROTOCOL_VERSION, "request_id": request_id, "job_id": control.job_id, "type": "progress", "stage": "started"})

            def progress(stage: str) -> None:
                emit({"protocol_version": PROTOCOL_VERSION, "request_id": request_id, "job_id": control.job_id, "type": "progress", "stage": stage})

            response = self.handle(request, control=control, progress=progress)
            with control.lock:
                control.finished = True
            with jobs_lock:
                jobs.pop(control.job_id, None)
            emit({**response, "job_id": control.job_id})

        try:
            for line in incoming:
                request: Any = None
                try:
                    request = json.loads(line)
                    if not isinstance(request, dict):
                        raise ProtocolError("E_REQUEST_INVALID", "Each input line must be a JSON object.")
                    kind, value, _params = self.validate_request(request)
                    if kind == "shutdown":
                        emit({
                            "protocol_version": PROTOCOL_VERSION,
                            "request_id": request.get("request_id"),
                            "type": "shutdown_accepted",
                        })
                        break
                    if kind == "cancel":
                        with jobs_lock:
                            job = jobs.get(value)
                        outcome = job[0].request_cancel() if job else "not_found"
                        emit({
                            "protocol_version": PROTOCOL_VERSION,
                            "request_id": request.get("request_id"),
                            "type": "cancel_result",
                            "job_id": value,
                            "status": outcome,
                            "message": "Cancellation is accepted only before the operation enters its write boundary.",
                        })
                        continue
                    control = JobControl()
                    with jobs_lock:
                        jobs[control.job_id] = (control, kind)
                    emit({
                        "protocol_version": PROTOCOL_VERSION,
                        "request_id": request.get("request_id"),
                        "type": "accepted",
                        "job_id": control.job_id,
                    })
                    executor.submit(run, request, control)
                except (json.JSONDecodeError, ProtocolError) as error:
                    code = error.code if isinstance(error, ProtocolError) else "E_REQUEST_JSON"
                    emit({
                        "protocol_version": PROTOCOL_VERSION,
                        "request_id": (
                            request.get("request_id")
                            if isinstance(request, dict)
                            and isinstance(request.get("request_id"), str)
                            else None
                        ),
                        "type": "result",
                        "status": "failed",
                        "error": {"code": code, "message": str(error)},
                    })
        finally:
            executor.shutdown(wait=True, cancel_futures=False)


def _file_version(path: Path) -> str | None:
    try:
        if path.is_symlink():
            return "symlink"
        if not path.is_file():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "unreadable"


def _walk_paths(value: Any) -> set[Path]:
    paths: set[Path] = set()
    if isinstance(value, PlannedChanges):
        paths.update(Path(path) for path in value.expected)
        for root in value.expected_trees:
            paths.add(Path(root))
        return paths
    if isinstance(value, Path):
        if value.is_file():
            paths.add(value)
        return paths
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, Path) and key.is_file():
                paths.add(key)
            paths.update(_walk_paths(item))
        return paths
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            paths.update(_walk_paths(item))
        return paths
    if is_dataclass(value):
        for field in fields(value):
            paths.update(_walk_paths(getattr(value, field.name)))
    return paths


def _stable(value: Any) -> Any:
    """Convert internal plans to deterministic, content-hash-only JSON values."""
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, PlannedChanges):
        return {
            "changes": {str(path): _stable(data) for path, data in value.items()},
            "expected": _stable(value.expected),
            "expected_trees": _stable(value.expected_trees),
            "metadata": _stable(value.metadata),
        }
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            label = str(key)
            if label in {"inventory_id", "generated_at", "saved", "created_at", "reported_at"}:
                continue
            normalized[label] = _stable(item)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_stable(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if is_dataclass(value):
        return {field.name: _stable(getattr(value, field.name)) for field in fields(value)}
    return repr(value)
