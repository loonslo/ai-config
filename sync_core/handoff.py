"""Project identity, code facts and readable task handoffs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit
import uuid

from .snapshots import load_snapshot, snapshot_confirmed
from .utils import SECRET, atomic_write, digest, json_bytes


REQUIRED_HEADINGS = {
    "goal": ("goal", "目標", "user goal", "使用者目標"),
    "acceptance": ("acceptance", "驗收", "acceptance criteria", "驗收條件"),
    "completed": ("completed", "已完成"),
    "remaining": ("remaining", "尚未完成", "待辦"),
    "decisions": ("decision", "決策"),
    "blockers": ("blocker", "阻塞"),
    "next_step": ("next", "下一步"),
    "tests": ("test", "測試"),
    "risks": ("risk", "風險"),
}
_PLACEHOLDER_LINES = {"todo", "tbd", "待填写", "待填", "未填写", "placeholder", "由当前助手或使用者填写。"}


def _validate_ids(project_id: str, handoff_id: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project_id) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", handoff_id):
        raise ValueError("Invalid project or handoff id")


@dataclass(frozen=True)
class CodeFacts:
    commit: str | None
    branch: str | None
    dirty_files: tuple[str, ...]
    lock_files: Mapping[str, str]
    remote: str | None
    remote_commit: str | None = None

    @property
    def ready(self) -> bool:
        return bool(self.commit and self.branch and not self.dirty_files and self.remote and self.commit == self.remote_commit)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return result.stdout.strip() if result.returncode == 0 else ""


def _dirty_files(root: Path) -> tuple[str, ...]:
    result = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if result.returncode:
        return ()
    return tuple(line[3:] if len(line) >= 4 else line for line in result.stdout.splitlines() if line.strip())


def _safe_remote(value: str) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc:
        host = parsed.hostname or ""
        netloc = host + (f":{parsed.port}" if parsed.port else "")
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    return value.split("@", 1)[-1]


def code_facts(root: Path) -> CodeFacts:
    commit = _git(root, "rev-parse", "HEAD") or None
    branch = _git(root, "branch", "--show-current") or None
    dirty = _dirty_files(root)
    lock_files: dict[str, str] = {}
    candidates = {"requirements.txt", "requirements.lock", "pyproject.toml", "poetry.lock", "uv.lock", "Pipfile.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
    for path in root.iterdir() if root.exists() else ():
        if path.is_file() and path.name in candidates:
            lock_files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    remote = _safe_remote(_git(root, "remote", "get-url", "origin"))
    remote_commit = _git(root, "ls-remote", "origin", f"refs/heads/{branch}") if remote and branch else ""
    remote_commit = remote_commit.split()[0] if remote_commit else None
    return CodeFacts(commit, branch, dirty, lock_files, remote, remote_commit)


def configuration_facts(root: Path, *, codex_keys: tuple[str, ...] = (), claude_keys: tuple[str, ...] = ()) -> dict[str, Any]:
    """Capture only portable ai-config facts, never local paths or credentials."""
    commit = _git(root, "rev-parse", "HEAD") or None
    branch = _git(root, "branch", "--show-current") or None
    dirty = _dirty_files(root)
    remote = _safe_remote(_git(root, "remote", "get-url", "origin"))
    remote_commit = _git(root, "ls-remote", "origin", f"refs/heads/{branch}") if remote and branch else ""
    remote_commit = remote_commit.split()[0] if remote_commit else None
    files: dict[str, str | None] = {}
    for relative in [*(f"common/{name}.md" for name in ("instructions", "principles", "engineering", "python", "langgraph", "rag", "security")), "codex/config.toml", "claude/settings.shared.json"]:
        path = root / relative
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    portable = {"schema_version": 1, "commit": commit, "branch": branch, "remote": remote, "remote_commit": remote_commit, "files": files, "codex_keys": sorted(codex_keys), "claude_keys": sorted(claude_keys)}
    portable["version"] = configuration_content_version(portable)
    portable["dirty_files"] = list(dirty)
    portable["missing_files"] = sorted(name for name, file_hash in files.items() if file_hash is None)
    portable["ready"] = bool(commit and remote and remote_commit == commit and not dirty and not portable["missing_files"])
    return portable


def configuration_content_version(facts: Mapping[str, Any]) -> str:
    """Runtime/remote observations do not change portable configuration content."""
    content = {key: facts.get(key) for key in ("schema_version", "files", "codex_keys", "claude_keys")}
    return hashlib.sha256(json_bytes(content)).hexdigest()


def register_project(memory_root: Path, project_id: str, project_root: Path, name: str | None = None) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project_id):
        raise ValueError("Invalid project id")
    target = memory_root / "registry" / "projects.json"
    if target.exists():
        registry = json.loads(target.read_text(encoding="utf-8"))
    else:
        registry = {"schema_version": 1, "projects": {}}
    existing = registry.setdefault("projects", {}).get(project_id, {})
    remote = _safe_remote(_git(project_root, "remote", "get-url", "origin"))
    if existing and existing.get("remote") != remote:
        raise ValueError("Project id is already registered to a different remote")
    record = {"id": project_id, "name": name or existing.get("name") or project_root.name, "remote": remote}
    registry["schema_version"] = 1
    registry["projects"][project_id] = record
    atomic_write(target, json_bytes(registry))
    return target


def validate_handoff(text: str) -> list[str]:
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_body: list[str] = []
    for line in lines:
        if line.lstrip().startswith("#"):
            if current_heading is not None:
                sections.append((current_heading, current_body))
            current_heading = line.lstrip("#").strip().casefold()
            current_body = []
        elif current_heading is not None:
            current_body.append(line)
    if current_heading is not None:
        sections.append((current_heading, current_body))
    missing: list[str] = []
    for key, names in REQUIRED_HEADINGS.items():
        matching = next((body for heading, body in sections if any(name.casefold() in heading for name in names)), None)
        if matching is None:
            missing.append(key)
            continue
        content = re.sub(r"<!--.*?-->", "", "\n".join(matching), flags=re.DOTALL).strip()
        if not content or content.casefold() in _PLACEHOLDER_LINES:
            missing.append(key)
    return missing


def save_handoff(
    memory_root: Path,
    *,
    project_id: str,
    text: str,
    project_root: Path,
    memory_snapshot: str | None = None,
    config_version: str | None = None,
    config_facts: Mapping[str, Any] | None = None,
    handoff_id: str | None = None,
) -> dict[str, Any]:
    if SECRET.search(text):
        raise ValueError("Potential secret in handoff; content was not saved")
    hid = handoff_id or uuid.uuid4().hex
    _validate_ids(project_id, hid)
    facts = code_facts(project_root)
    missing = validate_handoff(text)
    if memory_snapshot:
        manifest = load_snapshot(memory_root, memory_snapshot)
        if manifest.get("project_id") != project_id or manifest.get("tool") != "claude" or manifest.get("scope") != project_id:
            raise ValueError("Handoff memory snapshot does not match the project mapping")
    document_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    effective_config_version = config_facts.get("version") if config_facts else config_version
    payload: dict[str, Any] = {
        "schema_version": 1,
        "handoff_id": hid,
        "project_id": project_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if not missing and facts.ready and memory_snapshot and config_facts and config_facts.get("ready") else "incomplete",
        "missing_fields": missing,
        "code": {"commit": facts.commit, "branch": facts.branch, "dirty_files": list(facts.dirty_files), "lock_files": dict(facts.lock_files), "remote": facts.remote, "remote_commit": facts.remote_commit},
        "config_version": effective_config_version,
        "config": dict(config_facts) if config_facts else None,
        "memory_snapshot": memory_snapshot,
        "document_sha256": document_sha256,
        "document": text,
    }
    target = memory_root / "handoffs" / project_id / f"{hid}.json"
    markdown = memory_root / "handoffs" / project_id / f"{hid}.md"
    atomic_write(target, json_bytes({key: value for key, value in payload.items() if key != "document"}))
    atomic_write(markdown, text.encode("utf-8"))
    return payload


def load_handoff(memory_root: Path, project_id: str, handoff_id: str) -> dict[str, Any]:
    _validate_ids(project_id, handoff_id)
    target = memory_root / "handoffs" / project_id / f"{handoff_id}.json"
    if not target.exists():
        raise ValueError(f"Handoff not found: {project_id}/{handoff_id}")
    data = json.loads(target.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported handoff schema")
    if data.get("project_id") != project_id or data.get("handoff_id") != handoff_id:
        raise ValueError("Handoff identity does not match its path")
    return data


def start_report(memory_root: Path, project_id: str, handoff_id: str, project_root: Path, *, current_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    handoff = load_handoff(memory_root, project_id, handoff_id)
    current = code_facts(project_root)
    expected = handoff.get("code", {})
    errors: list[str] = []
    markdown = memory_root / "handoffs" / project_id / f"{handoff_id}.md"
    document_ok = False
    if markdown.exists() and isinstance(handoff.get("document_sha256"), str):
        document_ok = hashlib.sha256(markdown.read_bytes()).hexdigest() == handoff["document_sha256"]
    if not document_ok:
        errors.append("handoff document is missing or its hash does not match")
    snapshot_ok = False
    snapshot_error: str | None = None
    snapshot_id = handoff.get("memory_snapshot")
    if snapshot_id:
        try:
            manifest = load_snapshot(memory_root, snapshot_id)
            snapshot_ok = manifest.get("project_id") == project_id and manifest.get("scope") == project_id and manifest.get("tool") == "claude"
            if snapshot_ok and not snapshot_confirmed(memory_root, manifest):
                snapshot_ok = False
                snapshot_error = "memory snapshot is not remotely confirmed"
            if not snapshot_ok:
                snapshot_error = snapshot_error or "memory snapshot identity does not match this project"
        except (OSError, ValueError) as error:
            snapshot_error = str(error)
    else:
        snapshot_error = "memory snapshot is missing"
    if snapshot_error:
        errors.append(snapshot_error)
    registry_ok = False
    registry_path = memory_root / "registry" / "projects.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registered = registry.get("projects", {}).get(project_id, {})
        registry_ok = bool(registered.get("remote") and current.remote and registered.get("remote") == current.remote)
    except (OSError, ValueError):
        errors.append("project registry is missing or invalid")
    if not registry_ok:
        errors.append("project identity does not match the registered remote")
    checks = {
        "handoff_complete": handoff.get("status") in {"ready", "uploaded"},
        "handoff_content": not validate_handoff(markdown.read_text(encoding="utf-8")) if document_ok else False,
        "handoff_document_hash": document_ok,
        "snapshot_valid": snapshot_ok,
        "project_identity_matches": registry_ok,
        "code_clean": not current.dirty_files,
        "code_commit_matches": current.commit == expected.get("commit"),
        "branch_matches": current.branch == expected.get("branch"),
        "lock_files_match": dict(current.lock_files) == expected.get("lock_files", {}),
    }
    if current_config is not None and handoff.get("config"):
        checks["config_matches"] = configuration_content_version(current_config) == configuration_content_version(handoff["config"])
        checks["config_clean"] = not current_config.get("dirty_files") and not current_config.get("missing_files")
        if not checks["config_matches"]:
            errors.append("ai-config facts do not match the handoff")
    elif current_config is not None and handoff.get("config_version"):
        checks["config_matches"] = current_config.get("version") == handoff["config_version"]
        if not checks["config_matches"]:
            errors.append("ai-config version does not match the handoff")
    elif handoff.get("config_version"):
        checks["config_version_present"] = True
    else:
        checks["config_version_present"] = False
        errors.append("config version is missing")
    checks["handoff_complete"] = checks["handoff_complete"] and not errors
    return {"project_id": project_id, "handoff_id": handoff_id, "ready": all(checks.values()), "status": "ready" if all(checks.values()) else "incomplete", "checks": checks, "errors": errors, "snapshot_error": snapshot_error, "memory_snapshot": handoff.get("memory_snapshot")}
