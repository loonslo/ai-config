"""Source discovery with explicit missing, empty and unsupported states."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable
import uuid

from .config import DeviceConfig
from .merge import validate_file_map
from .utils import SECRET, atomic_write, digest, json_bytes


@dataclass(frozen=True)
class SourceReport:
    source_id: str
    tool: str
    status: str
    path: str | None
    project_id: str | None
    file_count: int
    files: tuple[str, ...]
    excluded: tuple[dict[str, str], ...] = ()
    detail: str | None = None
    version: str | None = None


def scan_source(path: Path, *, source_id: str, tool: str, project_id: str | None = None, exclude: Iterable[str] = (), version: str | None = None) -> SourceReport:
    excluded_names = set(exclude)
    if not path.exists():
        return SourceReport(source_id, tool, "missing", str(path), project_id, 0, (), version=version, detail="Source directory does not exist")
    if not path.is_dir():
        return SourceReport(source_id, tool, "unreadable", str(path), project_id, 0, (), version=version, detail="Source is not a directory")
    try:
        entries: dict[str, bytes] = {}
        for item in path.rglob("*"):
            if item.is_symlink():
                raise ValueError(f"Symlink requires manual migration: {item}")
            if item.is_file():
                relative = item.relative_to(path).as_posix()
                if relative in excluded_names:
                    continue
                if item.suffix != ".md":
                    return SourceReport(source_id, tool, "unsupported", str(path), project_id, 0, (), version=version, detail=f"Unsupported file type: {relative}")
                data = item.read_bytes()
                if SECRET.search(data.decode("utf-8")):
                    return SourceReport(source_id, tool, "blocked_secret", str(path), project_id, 0, (), version=version, detail="Potential secret detected; content omitted")
                entries[relative] = data
        clean = validate_file_map(entries)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        message = str(error)
        status = "path_collision" if "collision" in message.casefold() or "portable" in message.casefold() else "unreadable"
        return SourceReport(source_id, tool, status, str(path), project_id, 0, (), version=version, detail=message)
    if not clean and excluded_names:
        status = "intentionally_excluded"
    elif not clean:
        status = "normal_but_empty"
    else:
        status = "normal"
    excluded_records = tuple({"path": value, "reason": "configured exclusion"} for value in sorted(excluded_names))
    return SourceReport(source_id, tool, status, str(path), project_id, len(clean), tuple(clean), excluded_records, version=version)


def discover(config: DeviceConfig) -> dict[str, Any]:
    """Discover configured mappings plus likely tool roots needing mapping."""
    raw = config.raw
    versions = raw.get("tool_versions", {}) if isinstance(raw.get("tool_versions", {}), dict) else {}
    claude_version = versions.get("claude")
    codex_version = versions.get("codex")
    reports: list[SourceReport] = []
    mapped_claude: set[Path] = set()
    for item in raw.get("memories", []):
        path = config.path_value(item["path"])
        mapped_claude.add(path)
        reports.append(scan_source(path, source_id=f"claude:{item['id']}", tool="claude", project_id=item["id"], exclude=item.get("exclude", []), version=claude_version))

    claude_root = config.path("claude")
    if claude_root is None:
        reports.append(SourceReport("claude-root", "claude", "not_configured", None, None, 0, (), version=claude_version, detail="No claude root configured"))
    else:
        projects = claude_root / "projects"
        if projects.exists() and projects.is_dir():
            try:
                for candidate in sorted(projects.iterdir()):
                    memory = candidate / "memory"
                    if memory.is_dir() and memory not in mapped_claude:
                        reports.append(scan_source(memory, source_id=f"claude-unmapped:{candidate.name}", tool="claude", project_id=None, version=claude_version))
                        reports[-1] = SourceReport(**{**asdict(reports[-1]), "status": "pending_mapping"})
            except OSError as error:
                reports.append(SourceReport("claude-projects", "claude", "unreadable", str(projects), None, 0, (), version=claude_version, detail=str(error)))
        else:
            reports.append(SourceReport("claude-projects", "claude", "not_enabled", str(projects), None, 0, (), version=claude_version, detail="No Claude project memory root found"))

        # These roots are version-dependent and may be agent definitions or
        # other local data rather than portable memory.  If present, expose
        # them as pending mapping instead of silently treating them as synced.
        mapped_paths = set(mapped_claude)
        for relative in ("agents", "subagents", "memory"):
            candidate = claude_root / relative
            if candidate.exists() and candidate not in mapped_paths:
                discovered = scan_source(candidate, source_id=f"claude-candidate:{relative}", tool="claude", version=claude_version)
                reports.append(SourceReport(**{**asdict(discovered), "status": "pending_mapping", "detail": f"Potential Claude source; confirm mapping (scan={discovered.status})"}))

    codex_memory = config.path("codex_memory")
    if codex_memory is None:
        reports.append(SourceReport("codex-memory", "codex", "not_configured", None, None, 0, (), version=codex_version, detail="No Codex memory source configured"))
    else:
        reports.append(scan_source(codex_memory, source_id="codex-memory", tool="codex", version=codex_version))
    codex_root = config.path("codex")
    if codex_root is not None:
        for relative in ("agents", "memories"):
            candidate = codex_root / relative
            if candidate.exists() and candidate.resolve() != (codex_memory.resolve() if codex_memory else None):
                discovered = scan_source(candidate, source_id=f"codex-candidate:{relative}", tool="codex", version=codex_version)
                reports.append(SourceReport(**{**asdict(discovered), "status": "pending_mapping", "detail": f"Potential Codex source; export/reference only until mapped (scan={discovered.status})"}))

    for item in raw.get("additional_sources", []):
        path = config.path_value(item["path"])
        tool = item.get("tool", "unknown")
        discovered = scan_source(path, source_id=item["id"], tool=tool, project_id=item.get("project_id"), exclude=item.get("exclude", []), version=versions.get(tool))
        if item.get("status") == "intentionally_excluded":
            discovered = SourceReport(**{**asdict(discovered), "status": "intentionally_excluded", "detail": item.get("reason", "Configured exclusion")})
        reports.append(discovered)
    return {
        "schema_version": 1,
        "inventory_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "device_id": config.device,
        "sources": [asdict(report) for report in reports],
        "summary": {
            "total": len(reports),
            "ready": sum(report.status in {"normal", "normal_but_empty"} for report in reports),
            "pending_mapping": sum(report.status == "pending_mapping" for report in reports),
            "unavailable": sum(report.status in {"missing", "unreadable", "blocked_secret", "unsupported", "path_collision", "pending_mapping"} for report in reports),
        },
    }


def persist_report(config: DeviceConfig, report: dict[str, Any]) -> Path:
    target = config.state_dir / "inventory" / f"{report['inventory_id']}.json"
    atomic_write(target, json_bytes(report))
    return target


def source_files(path: Path, exclude: Iterable[str] = ()) -> dict[str, bytes]:
    """Read a checked source for callers that need the bytes after inventory."""
    report = scan_source(path, source_id="read", tool="unknown", exclude=exclude)
    if report.status not in {"normal", "normal_but_empty"}:
        raise ValueError(report.detail or f"Source unavailable: {path}")
    result: dict[str, bytes] = {}
    for name in report.files:
        result[name] = (path / name).read_bytes()
    return result


def _path_value(config: DeviceConfig, value: str) -> Path:
    return config.path_value(value)
