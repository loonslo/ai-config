"""Optional local-only configuration for the migration kit."""
from __future__ import annotations

from dataclasses import dataclass
import json
import ntpath
import os
from pathlib import Path
import posixpath
from typing import Any

from sync_core.layout import data_root
from .catalog import CODEX_DESKTOP_FIELDS
from .paths import RootMap


DEFAULT_EXCLUDES = (
    ".claude/worktrees/**", "**/scratch-workspaces/**", ".chatgpt-projects/**",
)
DEFAULT_PROCESSES = ("Claude.exe", "Codex.exe", "WorkBuddy.exe", "WorkBuddy AI.exe", "claude", "codex", "workbuddy")
_KEYS = frozenset({
    "core_projects", "exclude_patterns", "root_map", "instances",
    "include_desktop_fields", "allow_secret_hit_paths", "running_process_names",
})


@dataclass(frozen=True)
class MachineConfig:
    core_projects: tuple[Path, ...]
    exclude_patterns: tuple[str, ...]
    root_map: RootMap
    instances: dict[str, Path]
    include_desktop_fields: frozenset[str]
    allow_secret_hit_paths: frozenset[Path]
    running_process_names: tuple[str, ...]


def _path(value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("expected an absolute path or a home-relative path")
    if not (Path(value).is_absolute() or value.startswith("~/") or value.startswith("~\\")):
        raise ValueError("expected an absolute path or a home-relative path")
    return Path(os.path.abspath(Path(value).expanduser()))


def _mapping_path(value: Any, os_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("root_map paths must be absolute")
    if value.startswith(("~/", "~\\")):
        return str(Path(value).expanduser())
    absolute = ntpath.isabs(value) if os_name.casefold() in {"windows", "win32", "nt"} else posixpath.isabs(value)
    if not absolute:
        raise ValueError("root_map paths must be absolute")
    return value


def _list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{name} must be a list of nonempty strings")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate configuration key: {key}")
        result[key] = value
    return result


def load_config(path: Path | None = None, *, home: Path | None = None, source_os: str = "windows", target_os: str = "windows") -> MachineConfig:
    """Missing config uses safe defaults and never creates a file."""
    home = Path.home() if home is None else home
    location = data_root(home=home) / "machine.config.json" if path is None else Path(path)
    if location.is_symlink():
        raise ValueError("machine configuration may not be a symbolic link")
    data = json.loads(location.read_text(encoding="utf-8"), object_pairs_hook=_unique_object) if location.exists() else {}
    if not isinstance(data, dict) or set(data) - _KEYS:
        raise ValueError("unknown machine configuration keys")
    projects = tuple(_path(value) for value in _list(data.get("core_projects", []), "core_projects"))
    excludes = tuple(_list(data.get("exclude_patterns", list(DEFAULT_EXCLUDES)), "exclude_patterns"))
    mappings = data.get("root_map", [])
    if not isinstance(mappings, list) or any(not isinstance(item, dict) or set(item) != {"from", "to"} for item in mappings):
        raise ValueError("root_map must contain from/to pairs")
    root_map = RootMap(tuple((_mapping_path(item["from"], source_os), _mapping_path(item["to"], target_os)) for item in mappings), source_os, target_os)
    raw_instances = data.get("instances", {})
    if not isinstance(raw_instances, dict) or set(raw_instances) - {"workbuddy", "workbuddy-ai"}:
        raise ValueError("unknown machine instance")
    instances = {
        "workbuddy": _path(raw_instances.get("workbuddy", str(home / ".workbuddy"))),
        "workbuddy-ai": _path(raw_instances.get("workbuddy-ai", str(home / ".workbuddy-ai"))),
    }
    desktop = frozenset(_list(data.get("include_desktop_fields", []), "include_desktop_fields"))
    if desktop - CODEX_DESKTOP_FIELDS:
        raise ValueError("unsupported Codex desktop field")
    secrets = frozenset(_path(value) for value in _list(data.get("allow_secret_hit_paths", []), "allow_secret_hit_paths"))
    processes = tuple(_list(data.get("running_process_names", list(DEFAULT_PROCESSES)), "running_process_names"))
    return MachineConfig(projects, excludes, root_map, instances, desktop, secrets, processes)
