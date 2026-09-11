"""Validation and policy for local device configuration."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .utils import read_bytes

DEVICE_ID = re.compile(r"[a-z0-9][a-z0-9_-]*")
SHARED_CODEX_KEYS = frozenset({
    "approval_policy", "sandbox_mode", "web_search", "model_reasoning_effort",
    "project_doc_max_bytes",
})
SHARED_CLAUDE_KEYS = frozenset({"autoMemoryEnabled"})


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
    for key in ("state_dir", "memory_repo", "codex", "claude", "codex_memory"):
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
