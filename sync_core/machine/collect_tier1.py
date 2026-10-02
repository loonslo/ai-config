"""Read only approved Claude/Codex files into an in-memory bundle writer."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import tomllib
from typing import Any, Iterator, Mapping

from sync_core.rules_text import normalize, split_lines
from sync_core.utils import SECRET

from .bundle import BundleError, BundleWriter, MAX_FILE_BYTES
from .catalog import (
    CLAUDE_FIELDS_AUTO, CLAUDE_FIELDS_CONFIRM, CODEX_FIELDS_CONFIRM,
    allowed_item, denied_path,
)
from .config import MachineConfig, load_config
from .paths import derive_project_dir, git_root, norm

_ABSOLUTE = re.compile(r"(?i)(?:\b[A-Z]:[\\/]|(?<!\w)/(?:Users|home|workspace|Volumes)/)")


@dataclass
class CollectionResult:
    exclusions: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    files_by_kind: dict[str, int] = field(default_factory=dict)
    project_ids: list[str] = field(default_factory=list)
    source_fingerprints: dict[Path, tuple[str, int, Path]] = field(default_factory=dict, repr=False)

    def verify_sources_unchanged(self) -> bool:
        """Re-read only sources already touched by this collector."""
        for path, (digest, mtime, boundary) in self.source_fingerprints.items():
            try:
                data = _read(path, boundary)
                if hashlib.sha256(data).hexdigest() != digest or path.stat().st_mtime_ns != mtime:
                    return False
            except (OSError, BundleError):
                return False
        return True


def project_id(path: Path, os_name: str) -> str:
    key = norm(path, os_name)
    if os_name.casefold() in {"windows", "win32", "nt"}:
        key = key.casefold()
    return "p-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def _root(home: Path, environ: Mapping[str, str], agent: str) -> Path:
    key = "CLAUDE_CONFIG_DIR" if agent == "claude" else "CODEX_HOME"
    value = environ.get(key)
    root = Path(value).expanduser() if value else home / f".{agent}"
    if not root.is_absolute():
        raise ValueError("agent root must be absolute")
    return root


def _read(path: Path, boundary: Path) -> bytes:
    """Bounded read; reject links along the entire path and source changes."""
    if not path.is_relative_to(boundary):
        raise BundleError("source is outside approved root")
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise BundleError("symbolic link in source path")
        if candidate == boundary:
            break
    before = path.stat()
    if before.st_size > MAX_FILE_BYTES:
        raise BundleError("source file exceeds size limit")
    with path.open("rb") as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    after = path.stat()
    if len(data) > MAX_FILE_BYTES or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise BundleError("source file changed during read")
    return data


def _files_below(root: Path) -> Iterator[Path]:
    if not root.is_dir() or root.is_symlink():
        return
    for folder, directories, files in os.walk(root, followlinks=False):
        parent = Path(folder)
        directories[:] = [name for name in directories
                          if not (parent / name).is_symlink() and not denied_path(name)]
        for name in sorted(files):
            path = parent / name
            if path.is_file() and not path.is_symlink() and not denied_path(path.relative_to(root).as_posix()):
                yield path


def _flags(data: bytes, *, rules: bool) -> list[str]:
    text = data.decode("utf-8", errors="replace")
    flags = [f"abs_path:{sum(bool(_ABSOLUTE.search(line)) for line in text.splitlines())}"]
    if b"\x00" in data:
        flags.append("nontext")
    else:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            flags.append("nontext")
    if rules:
        lines = [normalize(line) for line in split_lines(text) if line.strip()]
        duplicates = len(lines) - len(set(lines))
        flags.append(f"duplicate_lines:{duplicates}/{len(lines)}")
    return flags


def _add_whole(writer: BundleWriter, result: CollectionResult, *, agent: str, source: Path,
               boundary: Path, relative: str, project: str | None = None,
               archive_relative: str | None = None,
               allow_secret_hit_paths: frozenset[Path] = frozenset()) -> None:
    item = allowed_item(agent, "main", relative)
    if item is None:
        return
    logical = f"{agent}:main/{relative}"
    try:
        if source.stat().st_size > MAX_FILE_BYTES:
            result.exclusions.append({"logical_path": logical, "source_path": str(source), "reason": "too_large"})
            return
        data = _read(source, boundary)
        result.source_fingerprints[source] = (hashlib.sha256(data).hexdigest(), source.stat().st_mtime_ns, boundary)
    except (OSError, BundleError):
        result.warnings.append({"code": "E7101", "message": "无法安全读取一个已选文件"})
        return
    flags = _flags(data, rules=item.kind == "rules")
    is_text = "nontext" not in flags
    if item.kind == "skills_text" and not is_text:
        result.exclusions.append({"logical_path": logical, "source_path": str(source), "reason": "non_text", "size": len(data),
                                  "sha256": hashlib.sha256(data).hexdigest()})
        return
    if SECRET.search(data.decode("utf-8", errors="replace")) and source not in allow_secret_hit_paths:
        result.exclusions.append({"logical_path": logical, "source_path": str(source), "reason": "secret_hit"})
        return
    archive_path = (f"files/{agent}/main/{relative}" if project is None
                    else f"files/projects/{project}/claude/memory/{archive_relative or source.name}")
    try:
        writer.add_file(archive_path, data, agent=agent, instance="main", kind=item.kind,
                        logical_path=logical, project_id=project, flags=flags)
    except BundleError:
        result.exclusions.append({"logical_path": logical, "source_path": str(source), "reason": "too_large"})
        return
    result.files_by_kind[item.kind] = result.files_by_kind.get(item.kind, 0) + 1


def _fields(writer: BundleWriter, result: CollectionResult, *, agent: str, source: Path, root: Path,
            selected_desktop: frozenset[str], os_name: str) -> None:
    if not source.is_file() or source.is_symlink():
        return
    try:
        data = _read(source, root)
        result.source_fingerprints[source] = (hashlib.sha256(data).hexdigest(), source.stat().st_mtime_ns, root)
        raw = json.loads(data) if agent == "claude" else tomllib.loads(data.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("settings root must be an object")
    except (OSError, BundleError, ValueError, UnicodeError):
        result.warnings.append({"code": "E7102", "message": "无法安全读取设置白名单字段"})
        return
    picked: dict[str, Any] = {}
    names: list[str] = []
    confirm: list[str] = []
    if agent == "claude":
        for key in CLAUDE_FIELDS_AUTO:
            if key in raw:
                picked[key] = raw[key]
                names.append(key)
        for key in CLAUDE_FIELDS_CONFIRM:
            if key in raw:
                picked[key] = raw[key]
                names.append(key)
                confirm.append(key)
        filename = "settings.fields.json"
        logical = "claude:main/settings.json"
    else:
        for key in ("model_reasoning_effort", "personality"):
            if key in raw:
                picked[key] = raw[key]
                names.append(key)
        for section in ("features", "memories"):
            if isinstance(raw.get(section), dict):
                picked[section] = raw[section]
                names.extend(f"{section}.{key}" for key in raw[section])
        for section, key in (("history", "persistence"), ("windows", "sandbox")):
            if section == "windows" and os_name.casefold() not in {"windows", "win32", "nt"}:
                continue
            if isinstance(raw.get(section), dict) and key in raw[section]:
                picked.setdefault(section, {})[key] = raw[section][key]
                names.append(f"{section}.{key}")
        if isinstance(raw.get("desktop"), dict):
            desktop = {key: raw["desktop"][key] for key in selected_desktop if key in raw["desktop"]}
            if desktop:
                picked["desktop"] = desktop
                names.extend(f"desktop.{key}" for key in desktop)
        for key in CODEX_FIELDS_CONFIRM:
            if key in raw:
                picked[key] = raw[key]
                names.append(key)
                confirm.append(key)
        filename = "config.fields.json"
        logical = "codex:main/config.toml"
    if not names:
        return
    try:
        derived = (json.dumps({"source": logical, "fields": picked}, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError):
        result.warnings.append({"code": "E7103", "message": "所选设置字段无法安全编码"})
        return
    if SECRET.search(derived.decode("utf-8")):
        result.exclusions.append({"logical_path": logical, "reason": "secret_hit"})
        return
    writer.add_file(f"files/{agent}/main/{filename}", derived, agent=agent, instance="main",
                    kind="settings_fields", mode="fields", logical_path=logical,
                    fields=sorted(names), confirm_fields=sorted(confirm))
    result.files_by_kind["settings_fields"] = result.files_by_kind.get("settings_fields", 0) + 1


def collect_tier1(writer: BundleWriter, *, home: Path, config: MachineConfig | None = None,
                  environ: Mapping[str, str] | None = None, agents: frozenset[str] = frozenset({"claude", "codex"}),
                  os_name: str | None = None) -> CollectionResult:
    """Never read credentials, login state, session DBs, or WorkBuddy drafts."""
    env = os.environ if environ is None else environ
    selected = config or load_config(home=home)
    system = os_name or platform.system().lower()
    result = CollectionResult()
    for agent in ("claude", "codex"):
        if agent not in agents:
            continue
        root = _root(home, env, agent)
        if not root.is_dir() or root.is_symlink():
            result.warnings.append({"code": "E7104", "message": f"{agent} 配置目录不存在或是链接，已跳过"})
            continue
        rule_names = ("CLAUDE.md",) if agent == "claude" else ("AGENTS.md", "AGENTS.override.md")
        for name in rule_names:
            source = root / name
            if source.is_file() and not source.is_symlink():
                _add_whole(writer, result, agent=agent, source=source, boundary=root, relative=name,
                           allow_secret_hit_paths=selected.allow_secret_hit_paths)
        if agent == "claude":
            for source in _files_below(root / "rules"):
                relative = source.relative_to(root).as_posix()
                _add_whole(writer, result, agent=agent, source=source, boundary=root, relative=relative,
                           allow_secret_hit_paths=selected.allow_secret_hit_paths)
            _fields(writer, result, agent=agent, source=root / "settings.json", root=root,
                    selected_desktop=selected.include_desktop_fields, os_name=system)
            visited: set[str] = set()
            for folder in selected.core_projects:
                if not folder.is_dir() or folder.is_symlink():
                    continue
                git_folder = git_root(folder)
                key = norm(git_folder, system).casefold() if system == "windows" else norm(git_folder, system)
                if key in visited:
                    continue
                visited.add(key)
                encoded = derive_project_dir(str(git_folder))
                if encoded is None:
                    result.warnings.append({"code": "E7105", "message": "一个项目路径过长，无法推导记忆目录"})
                    continue
                pid = project_id(git_folder, system)
                result.project_ids.append(pid)
                memory_root = root / "projects" / encoded / "memory"
                for source in _files_below(memory_root):
                    relative = source.relative_to(root).as_posix()
                    _add_whole(writer, result, agent=agent, source=source, boundary=root, relative=relative,
                               project=pid, archive_relative=source.relative_to(memory_root).as_posix(),
                               allow_secret_hit_paths=selected.allow_secret_hit_paths)
        else:
            _fields(writer, result, agent=agent, source=root / "config.toml", root=root,
                    selected_desktop=selected.include_desktop_fields, os_name=system)
            for source in _files_below(root / "skills"):
                relative = source.relative_to(root).as_posix()
                _add_whole(writer, result, agent=agent, source=source, boundary=root, relative=relative,
                           allow_secret_hit_paths=selected.allow_secret_hit_paths)
    return result
