"""Validation and policy for local device configuration."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

from .utils import read_bytes

DEVICE_ID = re.compile(r"[a-z0-9][a-z0-9_-]*")
SHARED_CODEX_KEYS = frozenset({
    "approval_policy", "sandbox_mode", "web_search", "model_reasoning_effort",
    "project_doc_max_bytes",
})
SHARED_CLAUDE_KEYS = frozenset({"autoMemoryEnabled"})

#: Managed rule topics.  These are the only common/ files written into tool
#: rule files; every entry is verified against the source before use.
SHARED_RULE_TOPICS = ("instructions", "principles", "engineering", "python", "langgraph", "rag", "security")

#: Keys that must never be treated as a shared managed field even if a device
#: configuration happens to name them.  Credentials and session state stay
#: local by construction.
FORBIDDEN_SHARED_KEYS = frozenset({
    "auth", "api_key", "apikey", "token", "access_token", "refresh_token",
    "password", "secret", "credentials", "session", "cookie", "cookies",
    "login", "oauth", "private_key", "mcp_servers", "model_provider",
    "providers", "env", "environment",
})


def is_forbidden_shared_key(key: str) -> bool:
    """Reject credential, login and session fields from the shared set."""
    lowered = key.strip().casefold()
    if lowered in FORBIDDEN_SHARED_KEYS:
        return True
    return any(token in lowered for token in ("token", "password", "secret", "credential", "api_key", "apikey"))


@dataclass(frozen=True)
class DeviceConfig:
    raw: dict[str, Any]
    source: Path | None = None

    @property
    def device(self) -> str:
        return self.raw["device"]

    @property
    def state_dir(self) -> Path:
        return absolute(self.raw["state_dir"])

    @property
    def memory_repo(self) -> Path:
        return absolute(self.raw["memory_repo"])

    def path(self, key: str) -> Path | None:
        value = self.raw.get(key)
        return absolute(value) if value else None

    def path_value(self, value: str) -> Path:
        return absolute(value)


def absolute(value: str | os.PathLike[str]) -> Path:
    path = Path(os.path.expandvars(str(value))).expanduser()
    if not path.is_absolute():
        raise ValueError(f"Use an absolute local path: {value}")
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError(f"Symlink path requires manual migration: {path}")
    return path.resolve()


def load(path: Path) -> DeviceConfig:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    validate(raw)
    return DeviceConfig(raw, path)


def validate(raw: dict[str, Any]) -> None:
    required = {"device", "state_dir", "memory_repo"}
    missing = sorted(required - raw.keys())
    if missing:
        raise ValueError("Missing device configuration fields: " + ", ".join(missing))
    if not isinstance(raw["device"], str) or not DEVICE_ID.fullmatch(raw["device"]):
        raise ValueError("Invalid device id")
    for key in ("state_dir", "memory_repo", "codex", "claude", "codex_memory", "config_repo"):
        if key in raw and raw[key] is not None and not isinstance(raw[key], str):
            raise ValueError(f"Configuration field must be a path string: {key}")
    state_path = absolute(raw["state_dir"])
    memory_path = absolute(raw["memory_repo"])
    if state_path == memory_path or memory_path in state_path.parents:
        raise ValueError("state_dir must not be inside memory_repo")
    for key, allowed in (("codex_keys", SHARED_CODEX_KEYS), ("claude_keys", SHARED_CLAUDE_KEYS)):
        values = raw.get(key, [])
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values) or len(values) != len(set(values)):
            raise ValueError(f"{key} must be a list of unique field names")
        forbidden = sorted(value for value in values if is_forbidden_shared_key(value))
        if forbidden:
            raise ValueError(f"Refusing to share credential or session {key}: {', '.join(forbidden)}")
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"Unsupported shared {key}: {', '.join(unknown)}")
    for key in ("codex_overrides", "claude_overrides"):
        if not isinstance(raw.get(key, {}), dict):
            raise ValueError(f"{key} must be an object")
    if not isinstance(raw.get("tool_versions", {}), dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in raw.get("tool_versions", {}).items()):
        raise ValueError("tool_versions must be an object of strings")
    additional_sources = raw.get("additional_sources", [])
    if not isinstance(additional_sources, list):
        raise ValueError("additional_sources must be a list")
    additional_ids: set[str] = set()
    for item in additional_sources:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not DEVICE_ID.fullmatch(item["id"]):
            raise ValueError("Each additional source needs a valid id")
        if item["id"] in additional_ids:
            raise ValueError("Duplicate additional source id")
        additional_ids.add(item["id"])
        if not isinstance(item.get("path"), str):
            raise ValueError(f"Additional source needs a path: {item['id']}")
        if not isinstance(item.get("tool", "unknown"), str):
            raise ValueError(f"Additional source tool must be a string: {item['id']}")
        if not isinstance(item.get("exclude", []), list) or any(not isinstance(v, str) for v in item.get("exclude", [])):
            raise ValueError(f"Additional source exclude must be a list of strings: {item['id']}")
    memories = raw.get("memories", [])
    if not isinstance(memories, list):
        raise ValueError("memories must be a list")
    ids: set[str] = set()
    for item in memories:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not DEVICE_ID.fullmatch(item["id"]):
            raise ValueError("Each memory mapping needs a valid id")
        if item["id"] in ids:
            raise ValueError("Duplicate memory id")
        ids.add(item["id"])
        if not isinstance(item.get("path"), str):
            raise ValueError(f"Memory mapping needs a path: {item['id']}")
        if not isinstance(item.get("exclude", []), list) or any(not isinstance(v, str) for v in item.get("exclude", [])):
            raise ValueError(f"Memory exclude must be a list of strings: {item['id']}")


def schema_version(raw: dict[str, Any]) -> int:
    value = raw.get("schema_version", 1)
    if not isinstance(value, int) or value < 1:
        raise ValueError("schema_version must be a positive integer")
    return value


def selected_codex_keys(raw: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the codex keys this device actually selected, not the allowlist."""
    return _selected(raw, "codex_keys", SHARED_CODEX_KEYS, "codex")


def selected_claude_keys(raw: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the claude keys this device actually selected, not the allowlist."""
    return _selected(raw, "claude_keys", SHARED_CLAUDE_KEYS, "claude")


def _selected(raw: Mapping[str, Any], field: str, allowed: frozenset[str], tool: str) -> tuple[str, ...]:
    values = raw.get(field, []) or []
    if not isinstance(values, list):
        raise ValueError(f"{field} must be a list of field names")
    result: dict[str, None] = {}
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must contain non-empty field names")
        if is_forbidden_shared_key(value):
            raise ValueError(f"Refusing to share a credential or session field: {tool}.{value}")
        if value not in allowed:
            # Unknown tool parameters are not managed by default; the device
            # must opt in through the allowlist once the parameter is verified.
            raise ValueError(f"{tool} field is not a verified shared parameter: {value}")
        result[value] = None
    return tuple(sorted(result))


def enabled_tools(raw: Mapping[str, Any]) -> tuple[str, ...]:
    """Detect which tool roots this device configured, in stable order."""
    return tuple(tool for tool in ("codex", "claude") if raw.get(tool))


def managed_fields(raw: Mapping[str, Any]) -> dict[str, list[str]]:
    """The complete managed-field selection for this device.

    Rule topics are always managed; tool configuration keys are managed only
    when the device selected them.
    """
    selection: dict[str, list[str]] = {"rules": list(SHARED_RULE_TOPICS)}
    if raw.get("codex"):
        selection["codex"] = list(selected_codex_keys(raw))
    if raw.get("claude"):
        selection["claude"] = list(selected_claude_keys(raw))
    return selection
