"""Collect only owner-approved WorkBuddy text candidates for manual restore."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterator, Mapping

from sync_core.utils import SECRET

from .bundle import BundleWriter
from .catalog import allowed_item, denied_path
from .collect_projects import _key, _owner
from .collect_tier1 import CollectionResult, _flags, _read, project_id
from .config import MachineConfig


_INSTANCES = ("workbuddy", "workbuddy-ai")
_SKIP = frozenset({".git", "node_modules", "worktrees"})


def _files(root: Path) -> Iterator[Path]:
    if not root.is_dir() or root.is_symlink():
        return
    for current, directories, files in os.walk(root, followlinks=False):
        folder = Path(current)
        directories[:] = [name for name in directories if not (folder / name).is_symlink()
                          and not denied_path((folder / name).relative_to(root).as_posix())]
        for name in sorted(files):
            source = folder / name
            if source.is_file() and not source.is_symlink() and not denied_path(source.relative_to(root).as_posix()):
                yield source


def _project_roots(project: Path, instance: str) -> Iterator[Path]:
    pending = [(project, 0)]
    while pending:
        folder, depth = pending.pop()
        if folder.is_symlink():
            continue
        candidate = folder / f".{instance}"
        if candidate.is_dir() and not candidate.is_symlink():
            yield candidate
        if depth == 2:
            continue
        try:
            with os.scandir(folder) as children:
                for child in children:
                    if child.name not in _SKIP and not child.name.startswith(".workbuddy") and child.is_dir(follow_symlinks=False):
                        pending.append((Path(child.path), depth + 1))
        except OSError:
            continue


def _add(writer: BundleWriter, result: CollectionResult, *, source: Path, boundary: Path,
         relative: str, archive: str, instance: str, scope: str, pid: str | None,
         logical_relative: str | None = None) -> None:
    item = allowed_item(instance, instance, relative, scope=scope)
    if item is None:
        return
    if item.kind == "memory" and source.suffix.casefold() != ".md":
        return
    logical = f"{instance}:{scope}/{logical_relative or relative}"
    try:
        data = _read(source, boundary)
        stat = source.stat()
    except (OSError, ValueError):
        result.warnings.append({"code": "E7301", "message": "一个 WorkBuddy 候选文件无法安全读取"})
        return
    digest = hashlib.sha256(data).hexdigest()
    result.source_fingerprints[source] = (digest, stat.st_mtime_ns, boundary)
    if b"\x00" in data:
        text = None
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = None
    if text is None:
        result.exclusions.append({"logical_path": logical, "source_path": str(source), "reason": "non_text", "size": len(data), "sha256": digest})
        return
    if SECRET.search(text):
        result.exclusions.append({"logical_path": logical, "source_path": str(source), "reason": "secret_hit"})
        return
    writer.add_file(archive, data, agent=instance, instance=instance, kind=item.kind,
                    logical_path=logical, project_id=pid, restore="manual", flags=_flags(data, rules=False))
    result.files_by_kind[item.kind] = result.files_by_kind.get(item.kind, 0) + 1


def collect_workbuddy(writer: BundleWriter, *, home: Path, config: MachineConfig,
                      agents: frozenset[str] = frozenset(_INSTANCES),
                      environ: Mapping[str, str] | None = None, os_name: str = "windows") -> CollectionResult:
    """Never open settings, account state, credentials, migration markers or DBs."""
    env = os.environ if environ is None else environ
    result = CollectionResult()
    for instance in _INSTANCES:
        if instance not in agents:
            continue
        root = config.instances.get(instance, Path(env.get(instance.upper().replace("-", "_") + "_HOME", str(home / f".{instance}"))))
        if not root.is_dir() or root.is_symlink():
            continue
        for name in ("BOOTSTRAP.md", "IDENTITY.md", "SOUL.md", "USER.md", "MEMORY.md"):
            source = root / name
            if source.is_file() and not source.is_symlink():
                _add(writer, result, source=source, boundary=root, relative=name,
                     archive=f"files/{instance}/{instance}/{name}", instance=instance, scope="agent", pid=None)
        for branch in ("memory", "skills"):
            for source in _files(root / branch):
                relative = source.relative_to(root).as_posix()
                _add(writer, result, source=source, boundary=root, relative=relative,
                     archive=f"files/{instance}/{instance}/{relative}", instance=instance, scope="agent", pid=None)
        visited: set[str] = set()
        for project in config.core_projects:
            if not project.is_dir() or project.is_symlink():
                continue
            identity = _key(project, os_name)
            if identity in visited:
                continue
            visited.add(identity)
            pid = project_id(project, os_name)
            for folder in _project_roots(project, instance):
                for branch in ("memory", "skills"):
                    for source in _files(folder / branch):
                        if _owner(str(source), config.core_projects, os_name) != _owner(str(project), config.core_projects, os_name):
                            continue
                        relative = source.relative_to(folder.parent).as_posix()
                        archive_relative = source.relative_to(project).as_posix()
                        _add(writer, result, source=source, boundary=project, relative=relative,
                             archive=f"files/projects/{pid}/{instance}/{archive_relative}",
                             instance=instance, scope="project", pid=pid,
                             logical_relative=archive_relative)
    return result
