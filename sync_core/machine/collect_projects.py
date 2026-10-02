"""Build a project profile from narrowly selected, read-only local sources."""
from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import closing
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import tomllib
from typing import Any, Mapping

from sync_core.utils import SECRET

from .bundle import BundleWriter
from .catalog import allowed_item
from .collect_tier1 import _read, project_id
from .config import MachineConfig
from .paths import derive_project_dir, git_root, norm


_ABSOLUTE = re.compile(r"(?i)(?:\b[A-Z]:[\\/]|(?<!\w)/(?:Users|home|workspace|Volumes)/)")
_SKIP = frozenset({".git", "node_modules", "worktrees"})


@dataclass
class ProjectResult:
    projects: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    dead_registered: int = 0
    known_paths: list[str] = field(default_factory=list)
    local_files: int = 0
    local_rules: int = 0
    local_absolute_rules: int = 0


def _key(path: str | os.PathLike[str], system: str) -> str:
    value = norm(path, system)
    return value.casefold() if system.casefold() in {"windows", "win32", "nt"} else value


def _inside(path: str, root: str, system: str) -> bool:
    value, base = _key(path, system), _key(root, system)
    return value == base or value.startswith(base.rstrip("/") + "/")


def _owner(path: str, projects: tuple[Path, ...], system: str) -> str | None:
    matches = [_key(project, system) for project in projects if _inside(path, str(project), system)]
    return max(matches, key=len) if matches else None


def _claude_registry(home: Path) -> dict[str, dict[str, bool]]:
    source = home / ".claude.json"
    if not source.is_file() or source.is_symlink():
        return {}
    try:
        raw = json.loads(_read(source, home))
        registered = raw.get("projects", {}) if isinstance(raw, dict) else {}
        result: dict[str, dict[str, bool]] = {}
        if isinstance(registered, dict):
            for path, fields in registered.items():
                if not isinstance(path, str) or not Path(path).is_absolute() or not isinstance(fields, dict):
                    continue
                result[path] = {name: fields.get(name) is True for name in
                                ("hasTrustDialogAccepted", "hasClaudeMdExternalIncludesApproved")}
        return result
    except (OSError, ValueError, UnicodeError):
        return {}


def _codex_registry(home: Path, environ: Mapping[str, str]) -> dict[str, str]:
    root = Path(environ.get("CODEX_HOME", str(home / ".codex")))
    source = root / "config.toml"
    if not source.is_file() or source.is_symlink():
        return {}
    try:
        raw = tomllib.loads(_read(source, root).decode("utf-8"))
        registered = raw.get("projects", {})
        if not isinstance(registered, dict):
            return {}
        return {path: fields["trust_level"] for path, fields in registered.items()
                if isinstance(path, str) and Path(path).is_absolute() and isinstance(fields, dict)
                and isinstance(fields.get("trust_level"), str)}
    except (OSError, ValueError, UnicodeError):
        return {}


def _sqlite_paths(home: Path, environ: Mapping[str, str], *, threads: bool = True) -> tuple[list[str], list[str], bool]:
    source = Path(environ.get("CODEX_HOME", str(home / ".codex"))) / "state_5.sqlite"
    if not source.is_file() or source.is_symlink():
        return [], [], False
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=1)) as connection:
            connection.execute("PRAGMA query_only=ON")
            roots = [row[0] for row in connection.execute("SELECT path FROM project_roots")
                     if isinstance(row[0], str)]
            cwd = ([row[0] for row in connection.execute("SELECT cwd FROM threads")
                    if isinstance(row[0], str)] if threads else [])
        return roots, cwd, True
    except (sqlite3.Error, OSError):
        return [], [], False


def _desktop_cwds(home: Path, environ: Mapping[str, str]) -> list[str]:
    appdata = Path(environ.get("APPDATA", str(home / "AppData" / "Roaming")))
    root = appdata / "Claude" / "claude-code-sessions"
    if not root.is_dir() or root.is_symlink():
        return []
    values: list[str] = []
    for source in root.glob("*.json"):
        if not source.is_file() or source.is_symlink():
            continue
        try:
            raw = json.loads(_read(source, root))
            if isinstance(raw, dict) and isinstance(raw.get("cwd"), str):
                values.append(raw["cwd"])
        except (OSError, ValueError, UnicodeError):
            continue
    return values


def _registered(home: Path, environ: Mapping[str, str]) -> tuple[dict[str, dict[str, bool]], dict[str, str], list[str], list[str], list[str], bool]:
    claude = _claude_registry(home)
    codex = _codex_registry(home, environ)
    roots, threads, sqlite_ok = _sqlite_paths(home, environ)
    desktop = _desktop_cwds(home, environ)
    return claude, codex, roots, threads, desktop, sqlite_ok


def known_folders(*, home: Path, environ: Mapping[str, str] | None = None,
                  os_name: str | None = None) -> list[str]:
    """Return only normalized folder names from the approved registries."""
    env = os.environ if environ is None else environ
    system = os_name or platform.system().lower()
    claude = _claude_registry(home)
    codex = _codex_registry(home, env)
    roots, _, _ = _sqlite_paths(home, env, threads=False)
    desktop = _desktop_cwds(home, env)
    found: dict[str, str] = {}
    for path in (*claude, *codex, *roots, *desktop):
        if isinstance(path, str) and Path(path).is_absolute():
            found.setdefault(_key(path, system), norm(path, system))
    return sorted(found.values(), key=str.casefold)


def _local_settings(root: Path) -> list[Path]:
    """Inspect only root, child and grandchild project folders."""
    result: list[Path] = []
    pending = [(root, 0)]
    while pending:
        current, depth = pending.pop()
        if current.is_symlink():
            continue
        candidate = current / ".claude" / "settings.local.json"
        if candidate.is_file() and not candidate.is_symlink():
            result.append(candidate)
        if depth == 2:
            continue
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.name not in _SKIP and entry.is_dir(follow_symlinks=False):
                        pending.append((Path(entry.path), depth + 1))
        except OSError:
            continue
    return sorted(result)


def collect_projects(writer: BundleWriter, *, home: Path, config: MachineConfig,
                     environ: Mapping[str, str] | None = None, os_name: str | None = None) -> ProjectResult:
    env = os.environ if environ is None else environ
    system = os_name or platform.system().lower()
    result = ProjectResult()
    claude, codex, roots, threads, desktop, sqlite_ok = _registered(home, env)
    if (Path(env.get("CODEX_HOME", str(home / ".codex"))) / "state_5.sqlite").exists() and not sqlite_ok:
        result.warnings.append({"code": "E7201", "message": "Codex 项目数据库无法只读打开或缺少所需表"})
    registered = (*claude, *codex, *roots)
    unique_registered = {_key(path, system): path for path in registered}
    result.dead_registered = sum(not Path(path).exists() for path in unique_registered.values())
    found: dict[str, str] = {}
    for path in (*registered, *desktop):
        if isinstance(path, str) and Path(path).is_absolute():
            found.setdefault(_key(path, system), norm(path, system))
    result.known_paths = sorted(found.values(), key=str.casefold)
    seen: set[str] = set()
    for configured in config.core_projects:
        project = Path(configured)
        root = git_root(project) if project.is_dir() and not project.is_symlink() else project
        identity = _key(project, system)
        if identity in seen:
            continue
        seen.add(identity)
        pid = project_id(project, system)
        root_identity = _key(root, system)
        trust = {"hasTrustDialogAccepted": False, "hasClaudeMdExternalIncludesApproved": False}
        claude_registered = False
        for path, fields in claude.items():
            if _key(path, system) == root_identity:
                claude_registered = True
                for name in trust:
                    trust[name] |= fields[name]
        codex_trust = next((value for path, value in codex.items() if _key(path, system) == root_identity), None)
        record = {
            "project_id": pid, "source_path": norm(project, system), "git_root": norm(root, system),
            "git_root_id": project_id(root, system),
            "exists": project.is_dir() and not project.is_symlink(), "claude_trust": trust,
            "codex_trust": codex_trust,
            "claude_session_count": 0,
            "desktop_session_count": sum(_owner(path, config.core_projects, system) == identity for path in desktop),
            "codex_thread_count": sum(_owner(path, config.core_projects, system) == identity for path in threads),
            "permissions_local_files": 0, "permissions_allow_rules": 0, "permissions_absolute_rules": 0,
        }
        encoded = derive_project_dir(str(project))
        if encoded is not None:
            session_dir = Path(env.get("CLAUDE_CONFIG_DIR", str(home / ".claude"))) / "projects" / encoded
            if session_dir.is_dir() and not session_dir.is_symlink():
                record["claude_session_count"] = sum(source.is_file() and not source.is_symlink()
                                                     for source in session_dir.glob("*.jsonl"))
        if record["exists"]:
            for source in _local_settings(project):
                if _owner(str(source), config.core_projects, system) != identity:
                    continue
                relative = source.relative_to(project).as_posix()
                if allowed_item("claude", "main", ".claude/settings.local.json", scope="project") is None:
                    break
                try:
                    data = _read(source, project)
                    parsed = json.loads(data)
                except (OSError, ValueError, UnicodeError):
                    result.warnings.append({"code": "E7202", "message": "一个项目本地权限文件无法安全读取"})
                    continue
                if SECRET.search(data.decode("utf-8", errors="replace")):
                    result.warnings.append({"code": "E7203", "message": "一个项目本地权限文件命中凭据特征，已跳过"})
                    continue
                permissions = parsed.get("permissions", {}) if isinstance(parsed, dict) else {}
                rules = permissions.get("allow", []) if isinstance(permissions, dict) else []
                rules = rules if isinstance(rules, list) else []
                absolute = sum(isinstance(item, str) and bool(_ABSOLUTE.search(item)) for item in rules)
                archive = f"files/projects/{pid}/claude/{relative}"
                writer.add_file(archive, data, agent="claude", instance="main", kind="permissions_local",
                                logical_path=f"project:{pid}/{relative}", project_id=pid,
                                flags=[f"abs_path:{absolute}"])
                record["permissions_local_files"] += 1
                record["permissions_allow_rules"] += len(rules)
                record["permissions_absolute_rules"] += absolute
                result.local_files += 1
                result.local_rules += len(rules)
                result.local_absolute_rules += absolute
        result.projects.append(record)
        if claude_registered:
            writer.add_file(f"files/projects/{pid}/claude/trust.fields.json",
                            (json.dumps({"fields": trust}, sort_keys=True) + "\n").encode(),
                            agent="claude", instance="main", kind="trust_fields", tier=2, mode="fields",
                            logical_path=f"project:{pid}/claude/trust", restore="manual", project_id=pid,
                            fields=list(trust))
        if codex_trust is not None:
            writer.add_file(f"files/projects/{pid}/codex/trust.fields.json",
                            (json.dumps({"trust_level": codex_trust}, sort_keys=True) + "\n").encode(),
                            agent="codex", instance="main", kind="trust_fields", mode="fields",
                            logical_path=f"project:{pid}/codex/trust", restore="confirm", project_id=pid,
                            fields=["trust_level"], confirm_fields=["trust_level"])
    writer.add_report("projects.json", json.dumps({"projects": result.projects,
                        "dead_registered": result.dead_registered, "known_folders": result.known_paths},
                        ensure_ascii=False, sort_keys=True) + "\n")
    return result
