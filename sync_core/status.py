"""User-facing consistency state for configuration, memory and handoff.

The module defines a single schema-versioned state document per device.  It is
deliberately split so that configuration status can be produced and verified
while memory remains disabled: the ``config`` capability never depends on the
``memory`` capability.

Two projections exist:

``build_state``
    Local-only view.  It may contain real absolute paths and observed local
    values because it never leaves the device.

``shared_receipt``
    The subset that is allowed to travel to the shared receipt branch.  It
    carries digests and non-sensitive metadata only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .utils import json_bytes

#: Supported versions of the portable state document.  An unknown version is
#: rejected explicitly instead of being coerced into the newest shape.
SUPPORTED_STATE_VERSIONS = (1,)
STATE_SCHEMA_VERSION = 1

#: Single authoritative status vocabulary.  ``ready`` is intentionally not a
#: member: a device is never "ready" as a whole, only "applied" per capability.
STATUS_CODES = (
    "not_configured",
    "pending_sync",
    "applied",
    "local_modified",
    "conflict",
    "offline",
    "apply_failed",
    "restart_required",
)

#: Capabilities are tracked separately so a configuration-only user never sees
#: an unrelated memory error.
CAPABILITIES = ("config", "memory", "handoff")

#: Field names that must never appear in a shared receipt.  These are matched
#: as object keys, never as substrings, so a legitimate value such as the tool
#: name ``claude`` is not confused with a local directory field.
_SENSITIVE_KEYS = frozenset({
    "url", "target", "path", "observed_digest", "detail", "device_path",
    "memory_repo", "state_dir", "codex", "claude", "codex_memory",
})

#: Keys that stay in a receipt even though they share a name with a local
#: device-configuration field.
_RECEIPT_ALLOWED_KEYS = frozenset({"claude", "codex"})


class StateSchemaError(ValueError):
    """The state document is malformed or uses an unsupported version."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def capability(*, enabled: bool, status: str, detail: str | None = None, checked_at: str | None = None) -> dict[str, Any]:
    """Build one capability record with a validated status code."""
    if status not in STATUS_CODES:
        raise StateSchemaError(f"Unknown capability status: {status}")
    return {"enabled": bool(enabled), "status": status, "detail": detail, "checked_at": checked_at}


def build_state(
    *,
    device_id: str,
    source: Mapping[str, Any],
    capabilities: Mapping[str, Mapping[str, Any]],
    managed: Mapping[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble a validated local state document.

    ``capabilities`` must contain exactly the three known capabilities; the
    caller supplies each one independently rather than a single combined flag.
    """
    missing = sorted(set(CAPABILITIES) - set(capabilities))
    if missing:
        raise StateSchemaError("State must describe every capability: " + ", ".join(missing))
    unknown = sorted(set(capabilities) - set(CAPABILITIES))
    if unknown:
        raise StateSchemaError("Unknown capability: " + ", ".join(unknown))
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "device_id": device_id,
        "generated_at": generated_at or _now(),
        "source": dict(source),
        "capabilities": {name: dict(capabilities[name]) for name in CAPABILITIES},
        "managed": dict(managed),
    }
    validate_state(state)
    return state


def validate_state(state: Mapping[str, Any]) -> None:
    """Reject unknown versions and malformed status fields early."""
    if not isinstance(state, Mapping):
        raise StateSchemaError("State must be an object")
    version = state.get("schema_version")
    if not isinstance(version, int):
        raise StateSchemaError("State schema_version must be an integer")
    if version not in SUPPORTED_STATE_VERSIONS:
        raise StateSchemaError(f"Unsupported state schema version: {version}")
    device = state.get("device_id")
    if not isinstance(device, str) or not device:
        raise StateSchemaError("State requires a device_id")
    source = state.get("source")
    if not isinstance(source, Mapping) or source.get("status") not in STATUS_CODES:
        raise StateSchemaError("State source requires a known status")
    capabilities = state.get("capabilities")
    if not isinstance(capabilities, Mapping):
        raise StateSchemaError("State requires a capabilities object")
    for name in CAPABILITIES:
        record = capabilities.get(name)
        if not isinstance(record, Mapping):
            raise StateSchemaError(f"State is missing capability: {name}")
        if not isinstance(record.get("enabled"), bool):
            raise StateSchemaError(f"Capability {name} requires an explicit enabled flag")
        if record.get("status") not in STATUS_CODES:
            raise StateSchemaError(f"Capability {name} has an unknown status: {record.get('status')}")
    managed = state.get("managed")
    if not isinstance(managed, Mapping) or not isinstance(managed.get("targets", []), list):
        raise StateSchemaError("State requires a managed object with a targets list")
    config = capabilities["config"]
    # Configuration must be able to succeed with memory disabled; an enabled
    # memory capability is never a precondition for a config status.
    if not config["enabled"] and config["status"] == "applied":
        raise StateSchemaError("Configuration cannot be applied while it is disabled")


def upgrade_check(state: Mapping[str, Any]) -> str:
    """Return the version after confirming it is supported, else raise."""
    validate_state(state)
    return str(state["schema_version"])


def _strip(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _strip(item)
            for key, item in value.items()
            if key not in _SENSITIVE_KEYS or key in _RECEIPT_ALLOWED_KEYS
        }
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value


def shared_receipt(state: Mapping[str, Any]) -> dict[str, Any]:
    """Project a local state into the publishable receipt subset.

    Real paths, observed local digests and free-form details are dropped: only
    the explicitly allowed digests and non-sensitive metadata survive.
    """
    validate_state(state)
    managed = state.get("managed", {})
    config = state.get("capabilities", {}).get("config", {})
    source = state.get("source", {})
    targets = []
    for target in managed.get("targets", []):
        if not isinstance(target, Mapping):
            continue
        entry = {
            "tool": target.get("tool"),
            "target_kind": target.get("target_kind"),
            "expected_digest": target.get("expected_digest"),
            "status": target.get("status"),
        }
        if "load_check" in target:
            # Only the outcome travels; the answer and the check time stay local.
            entry["load_verified"] = target.get("load_check") == "verified"
        targets.append(entry)
    receipt = {
        "schema_version": 1,
        "device_id": state.get("device_id"),
        "reported_at": _now(),
        "source_identity": source.get("identity"),
        "source_commit": source.get("commit"),
        "applied_version": managed.get("last_applied_version"),
        "applied_at": managed.get("last_applied_at"),
        "shared_fields": _strip(managed.get("shared_fields", {})),
        "target_digests": targets,
        "config_status": config.get("status"),
    }
    return receipt


def receipt_is_sensitive_free(receipt: Mapping[str, Any]) -> bool:
    """Guard used by tests and the receipt writer: no local-only key leaks.

    Keys are compared exactly and only where they are actually object keys, so
    the tool name ``claude`` may appear as a value without failing the check.
    """
    def walk(value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if isinstance(key, str) and key in _SENSITIVE_KEYS and key not in _RECEIPT_ALLOWED_KEYS:
                    return False
                if not walk(item):
                    return False
        elif isinstance(value, list):
            return all(walk(item) for item in value)
        return True

    return walk(receipt)
