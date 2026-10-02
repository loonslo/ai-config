"""Memory snapshot and project handoff workflows used by the application API."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ..config import absolute
from ..handoff import (
    code_facts,
    configuration_facts,
    register_project,
    save_handoff,
    start_report,
    validate_handoff,
)
from ..memory_io import stable_files
from ..merge import three_way_merge
from ..planning import memory_baseline, source_root
from ..snapshots import create_snapshot, load_snapshot, mark_head_confirmed, snapshot_files
from ..transaction import PlannedChanges, SyncLock, transaction
from ..utils import digest, json_bytes


class ContinuationError(RuntimeError):
    """A continuation operation failed with a stable process-facing status."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def project_path(config: Mapping[str, Any], project_id: str) -> Path:
    projects = config.get("projects", config.get("project_paths", {}))
    value = projects.get(project_id) if isinstance(projects, Mapping) else None
    if not value:
        raise ValueError(f"No local project path configured for project: {project_id}")
    return absolute(value)


def memory_mapping(config: Mapping[str, Any], project_id: str) -> dict[str, Any]:
    for item in config.get("memories", []):
        if item.get("id") == project_id:
            return dict(item)
    raise ValueError(f"No memory mapping configured for project: {project_id}")


def config_facts(config: Mapping[str, Any], *, default_root: Path | None = None) -> dict[str, Any]:
    from ..config import selected_claude_keys, selected_codex_keys

    return configuration_facts(
        source_root(config, default_root=default_root),
        codex_keys=tuple(selected_codex_keys(config)),
        claude_keys=tuple(selected_claude_keys(config)),
    )


def snapshot_for_finish(config: Mapping[str, Any], project_id: str) -> dict[str, Any]:
    item = memory_mapping(config, project_id)
    source = absolute(item["path"])
    if not source.is_dir():
        raise ValueError(f"Memory source missing; finish cannot generate a deletion event: {source}")
    memory_root = absolute(config["memory_repo"])
    head = memory_root / "heads" / config["device"] / f"{project_id}.json"
    parent = json.loads(head.read_text(encoding="utf-8")).get("snapshot_id") if head.exists() else None
    current = stable_files(source, item.get("exclude", []))
    branch = code_facts(project_path(config, project_id)).branch or "detached"
    branch_id = hashlib.sha256(branch.encode("utf-8")).hexdigest()[:16]
    return create_snapshot(
        memory_root,
        device=config["device"],
        scope=project_id,
        project_id=project_id,
        branch_id=branch_id,
        files=current,
        parent_snapshot=parent,
        source_id=f"claude:{project_id}",
    )


def finish_preview(
    config: dict[str, Any], project_id: str, handoff_file: Path | None, *, handoff_text: str | None = None, default_root: Path | None = None
) -> dict[str, Any]:
    from ..transport import GitTransport

    project_root = project_path(config, project_id)
    item = memory_mapping(config, project_id)
    source = absolute(item["path"])
    if not source.is_dir():
        raise ValueError(f"Memory source missing; finish cannot generate a deletion event: {source}")
    text = handoff_text if handoff_text is not None else handoff_file.read_text(encoding="utf-8") if handoff_file is not None else None
    if text is None:
        raise ValueError("A handoff document is required.")
    facts = code_facts(project_root)
    portable_config = config_facts(config, default_root=default_root)
    memory_root = absolute(config["memory_repo"])
    return {
        "project_id": project_id,
        "status": "preview",
        "handoff_missing_fields": validate_handoff(text),
        "code_ready": facts.ready,
        "code_branch": facts.branch,
        "code_dirty_files": list(facts.dirty_files),
        "memory_file_count": len(stable_files(source, item.get("exclude", []))),
        "memory_repository_exists": memory_root.exists(),
        "memory_remote_configured": GitTransport(memory_root).has_remote() if (memory_root / ".git").exists() else False,
        "config_ready": portable_config["ready"],
        "config_version": portable_config["version"],
        "config_dirty_files": portable_config["dirty_files"],
    }


def finish_apply(
    config: dict[str, Any], project_id: str, handoff_file: Path | None, *, handoff_text: str | None = None, default_root: Path | None = None
) -> dict[str, Any]:
    from ..transport import GitTransport, TransportPending

    project_root = project_path(config, project_id)
    memory_root = absolute(config["memory_repo"])
    memory_root.mkdir(parents=True, exist_ok=True)
    state = absolute(config["state_dir"])
    with SyncLock(state):
        snapshot = snapshot_for_finish(config, project_id)
        register_project(memory_root, project_id, project_root)
        text = handoff_text if handoff_text is not None else handoff_file.read_text(encoding="utf-8") if handoff_file is not None else None
        if text is None:
            raise ValueError("A handoff document is required.")
        portable_config = config_facts(config, default_root=default_root)
        payload = save_handoff(
            memory_root,
            project_id=project_id,
            text=text,
            project_root=project_root,
            memory_snapshot=snapshot["snapshot_id"],
            config_facts=portable_config,
        )
        target = memory_root / "handoffs" / project_id / f"{payload['handoff_id']}.json"

        def update_handoff() -> None:
            from ..utils import atomic_write

            target_data = json.loads(target.read_text(encoding="utf-8"))
            target_data.update({key: value for key, value in payload.items() if key != "document"})
            atomic_write(target, json_bytes(target_data))

        if not portable_config["ready"]:
            payload["status"] = "incomplete"
            payload["transport"] = "not_started"
            payload["config_error"] = "ai-config has uncommitted changes or is not confirmed on its remote"
            update_handoff()
            return payload
        if payload["status"] != "ready":
            payload["transport"] = "not_started"
            update_handoff()
            return payload

        try:
            result = GitTransport(memory_root).push_confirmed()
            mark_head_confirmed(memory_root, config["device"], project_id)
            payload["transport"] = result.status
            payload["status"] = "uploaded"
            update_handoff()
            GitTransport(memory_root).push_confirmed()
        except (TransportPending, RuntimeError, ValueError) as error:
            payload["transport"] = "pending"
            payload["transport_detail"] = str(error)
            payload["status"] = "pending"
            update_handoff()
    return payload


def start_plan(
    config: dict[str, Any], project_id: str, report: dict[str, Any], *, apply: bool, state: Path
) -> PlannedChanges:
    snapshot_id = report.get("memory_snapshot")
    if not snapshot_id:
        raise ContinuationError("Start cannot continue: the handoff has no memory snapshot", 2)
    item = memory_mapping(config, project_id)
    memory_root = absolute(config["memory_repo"])
    manifest = load_snapshot(memory_root, snapshot_id)
    if manifest.get("project_id") != project_id or manifest.get("scope") != project_id or manifest.get("tool") != "claude":
        raise ContinuationError("Start cannot continue: the handoff snapshot is for another project or tool", 4)
    target = absolute(item["path"])
    if target == memory_root or target in memory_root.parents or memory_root in target.parents:
        raise ValueError("Local and shared memory roots overlap")
    local = stable_files(target, item.get("exclude", []))
    pre_start_snapshot_id: str | None = None
    if apply:
        branch = code_facts(project_path(config, project_id)).branch or "detached"
        branch_id = "start-local-" + hashlib.sha256(branch.encode("utf-8")).hexdigest()[:12]
        with SyncLock(state):
            local_snapshot = create_snapshot(
                memory_root,
                device=config["device"],
                scope=f"start-{project_id}",
                project_id=project_id,
                branch_id=branch_id,
                files=local,
                source_id=f"claude:{project_id}:pre-start",
            )
        pre_start_snapshot_id = local_snapshot["snapshot_id"]
    remote = snapshot_files(memory_root, manifest)
    marker = state / f"memory-{project_id}.json"
    marker_data = marker.read_bytes() if marker.exists() else None
    base = memory_baseline(marker) if marker_data is not None else {}
    if marker_data is None and local and local != remote:
        raise ContinuationError("Receiver baseline missing; restore its confirmed baseline before merging", 4)
    merged_result = three_way_merge(local, remote, base)
    if merged_result.conflicts:
        raise ContinuationError(
            "Start found memory conflicts; local content was not changed (pre-start snapshot "
            + (pre_start_snapshot_id or "not persisted in preview") + "): "
            + ", ".join(conflict.path for conflict in merged_result.conflicts),
            4,
        )
    merged = merged_result.files
    for name, data in merged.items():
        if data is not None and name not in local and name not in remote:
            raise ContinuationError(f"Start produced an unsafe memory path: {name}", 4)
    deletions = [name for name in set(local) - set(merged) if name in local]
    if deletions:
        raise ContinuationError(
            "Start would delete local memory; resolve the deletion explicitly before applying: " + ", ".join(sorted(deletions)),
            4,
        )
    shared_target = memory_root / "claude" / project_id
    shared_current = stable_files(shared_target) if shared_target.exists() else {}
    if shared_current and shared_current != remote:
        raise ContinuationError("Start found unpublished changes in the local memory repository; preserve them before continuing", 4)
    changes: dict[Path, bytes | None] = {}
    expected: dict[Path, str | None] = {}
    for name in sorted(set(local) | set(merged)):
        data = merged.get(name)
        path = target / name
        current = path.read_bytes() if path.exists() else None
        if current != data:
            changes[path] = data
        expected[path] = digest(current)
    for name in sorted(set(shared_current) | set(merged)):
        data = merged.get(name)
        path = shared_target / name
        current = path.read_bytes() if path.exists() else None
        if current != data:
            changes[path] = data
        expected[path] = digest(current)
    marker_result = json.dumps(
        {"schema_version": 1, "files": {name: digest(data) for name, data in merged.items()}},
        sort_keys=True,
    ).encode("utf-8")
    marker_path = state / f"memory-{project_id}.json"
    if marker_result != marker_data:
        changes[marker_path] = marker_result
    expected[marker_path] = digest(marker_data)
    plan = PlannedChanges(
        changes,
        expected=expected,
        expected_trees={
            target: {name: digest(data) or "" for name, data in local.items()},
            shared_target: {name: digest(data) or "" for name, data in shared_current.items()},
        },
        state_root=state,
        metadata={"operation": "start", "snapshot_id": snapshot_id, "project_id": project_id},
    )
    if pre_start_snapshot_id:
        plan.metadata["pre_start_snapshot"] = pre_start_snapshot_id
    if apply:
        if not report["ready"]:
            raise ContinuationError("Start is not ready; resolve the reported handoff/configuration checks before applying", 2)
        with SyncLock(state):
            transaction(plan, state / "backups", state_root=state, lock=False)
    return plan


def start(
    config: dict[str, Any],
    project_id: str,
    handoff_id: str,
    *,
    apply: bool,
    state: Path,
    default_root: Path | None = None,
) -> dict[str, Any]:
    from ..transport import GitTransport

    memory_root = absolute(config["memory_repo"])
    if apply and (memory_root / ".git").exists():
        transport = GitTransport(memory_root)
        if transport.has_remote():
            try:
                with SyncLock(state):
                    transport.pull_ff_only()
            except RuntimeError as error:
                raise ContinuationError(f"Start cannot fetch the memory repository: {error}", 3) from error
    project_root = project_path(config, project_id)
    report = start_report(
        memory_root,
        project_id,
        handoff_id,
        project_root,
        current_config=config_facts(config, default_root=default_root),
    )
    if not report["ready"]:
        report["status"] = "incomplete"
        return report
    plan = start_plan(config, project_id, report, apply=apply, state=state)
    report["status"] = "ready" if apply else "preview"
    return {**report, "changes": len(plan), "paths": [str(path) for path in plan]}
