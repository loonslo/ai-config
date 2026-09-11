"""Read-only integrity and continuation diagnostics."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import DeviceConfig
from .inventory import discover, persist_report
from .snapshots import load_snapshot
from .transport import GitTransport
from .transaction import recover_transactions
from .utils import process_is_alive
import json


def run(config: DeviceConfig) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}
    state = config.state_dir
    lock = state / "sync.lock"
    if lock.exists():
        try:
            payload = json.loads(lock.read_text(encoding="utf-8"))
            pid = payload.get("pid")
        except (OSError, ValueError):
            pid = None
        if isinstance(pid, int) and process_is_alive(pid):
            issues.append("A sync operation is currently running")
        else:
            warnings.append("A stale sync lock is present; the next operation can recover it")
    journals = recover_transactions(state)
    pending = [item for item in journals if item.get("status") in {"PREPARED", "APPLYING", "INTERRUPTED", "ROLLBACK_REQUIRED"}]
    if pending:
        issues.append(f"{len(pending)} incomplete transaction(s) require rollback review")
    if any(item.get("status") == "INVALID_JOURNAL" for item in journals):
        issues.append("An unreadable transaction journal requires manual review")
    inventory = discover(config)
    for source in inventory["sources"]:
        if source["status"] in {"missing", "unreadable", "blocked_secret", "pending_mapping", "unsupported", "path_collision"}:
            issues.append(f"{source['source_id']}: {source['status']}")
        elif source["status"] == "not_configured":
            warnings.append(f"{source['source_id']}: not configured")
    checks["memory_repository_exists"] = config.memory_repo.exists()
    if not checks["memory_repository_exists"]:
        warnings.append("Memory repository does not exist yet")
    else:
        if not (config.memory_repo / ".git").exists():
            warnings.append("Memory repository is not a Git repository yet")
        heads = []
        for head_path in sorted((config.memory_repo / "heads").glob("*/*.json")):
            try:
                head = json.loads(head_path.read_text(encoding="utf-8"))
                manifest = load_snapshot(config.memory_repo, head["snapshot_id"], device=head["device_id"])
                heads.append({"device_id": head.get("device_id"), "scope": head.get("scope"), "snapshot_id": head.get("snapshot_id"), "status": head.get("status")})
                if head.get("manifest_sha256") != manifest.get("manifest_sha256"):
                    issues.append(f"Snapshot head hash mismatch: {head_path.name}")
                if head.get("status") != "uploaded":
                    warnings.append(f"Snapshot head is not remotely confirmed: {head_path.name}")
            except (OSError, ValueError, KeyError) as error:
                issues.append(f"Invalid snapshot head: {head_path.name}")
        checks["snapshot_heads"] = heads
        if (config.memory_repo / ".git").exists() and not GitTransport(config.memory_repo).clean():
            issues.append("Memory repository has unpublished local changes")
    transport_state = state / "transport.json"
    if transport_state.exists():
        try:
            transport = json.loads(transport_state.read_text(encoding="utf-8"))
            checks["transport"] = {"status": transport.get("status"), "commit": transport.get("commit")}
            if transport.get("status") == "pending":
                issues.append("Memory Git transport is pending; retry after preserving the local commit")
        except (OSError, ValueError):
            issues.append("Transport state is unreadable")
    checks["inventory"] = inventory["summary"]
    checks["transactions"] = [{"operation_id": item.get("operation_id"), "status": item.get("status")} for item in journals]
    return {"schema_version": 1, "device_id": config.device, "ok": not issues, "issues": issues, "warnings": warnings, "checks": checks}
