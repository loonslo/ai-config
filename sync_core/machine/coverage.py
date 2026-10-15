"""Metadata-only coverage observation, independent of legacy collection."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Callable, Iterator, Mapping

from .catalog import Decision, classify, classify_field
from .privacy import personal_text, private_text


def safe_name(value: str) -> str:
    """Do not echo email-shaped or credential-shaped names in reports."""
    return "<名称已隐藏>" if personal_text(value) or private_text(value) else value


def is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def no_links(path: Path) -> bool:
    return not any(is_link(p) for p in (path, *path.parents))


@dataclass(frozen=True)
class ApprovedLink:
    link: str
    targets: tuple[str, ...]


@dataclass(frozen=True)
class SourceRoot:
    id: str
    agent: str
    instance: str
    resolve: Callable[[Path, Mapping[str, str]], Path | None]
    links: tuple[ApprovedLink, ...] = ()


@dataclass(frozen=True)
class Limits:
    max_entries: int = 100_000
    max_depth: int = 64
    max_file_bytes: int = 64 * 1024 * 1024
    groups: frozenset[str] | None = None


@dataclass(frozen=True)
class Candidate:
    root: SourceRoot
    path: Path
    relative: str
    size: int
    decision: Decision


def observe_fields(raw: dict, *, root: str, source: str, ledger: Ledger) -> None:
    """Observe names from bytes a collector already parsed; retain no values."""
    def visit(value: dict, prefix: str = "") -> None:
        for key, child in value.items():
            if not isinstance(key, str):
                continue
            # Project registration keys contain absolute paths; report schema
            # selectors rather than identifiers or machine-specific key names.
            name = "*" if prefix == "projects" else key
            dotted = f"{prefix}.{name}" if prefix else name
            decision = classify_field(root, source, dotted)
            if isinstance(child, dict) and child and decision.action != "never":
                visit(child, dotted)
            else:
                ledger.field(f"{root}/{source}", dotted, decision)
    visit(raw)


@dataclass
class Ledger:
    _roots: dict[str, dict] = field(default_factory=dict)
    _seen: set[tuple[str, str]] = field(default_factory=set, repr=False)
    _decisions: dict[tuple[str, str], Decision] = field(default_factory=dict, repr=False)
    _carried: set[tuple[str, str]] = field(default_factory=set, repr=False)
    _fields: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def root(self, root: str, present: bool) -> None:
        self._roots.setdefault(root, {"id": root, "present": present, "files": 0, "bytes": 0,
                                     "by_nature": {}, "pruned": [], "unclassified": {"count": 0, "samples": []},
                                     "complete": True, "issues": []})

    def issue(self, root: str, reason: str) -> None:
        self._roots[root]["complete"] = False
        if reason not in self._roots[root]["issues"]:
            self._roots[root]["issues"].append(reason)

    def seen(self, root: str, relative: str, size: int, decision: Decision) -> None:
        if (root, relative) in self._seen:
            raise ValueError("duplicate coverage observation")
        self._seen.add((root, relative))
        self._decisions[root, relative] = decision
        self.root(root, True)
        record = self._roots[root]
        record["files"] += 1
        record["bytes"] += size
        bucket = record["by_nature"].setdefault(decision.nature, {"files": 0, "bytes": 0, "carried": 0})
        bucket["files"] += 1
        bucket["bytes"] += size
        if decision.nature == "U":
            record["unclassified"]["count"] += 1
            if len(record["unclassified"]["samples"]) < 20:
                record["unclassified"]["samples"].append(safe_name(relative))

    def carried(self, root: str, relative: str, decision: Decision) -> None:
        key = root, relative
        if key in self._seen and key not in self._carried:
            self._carried.add(key)
            self._roots[root]["by_nature"][self._decisions[key].nature]["carried"] += 1

    def pruned(self, root: str, relative: str, rule_id: str, entries: int) -> None:
        self.root(root, True)
        self._roots[root]["pruned"].append({"path": safe_name(relative), "rule_id": rule_id, "entries": entries})

    def field(self, source: str, key: str, decision: Decision) -> None:
        record = self._fields.setdefault(safe_name(source), {name: [] for name in
                                          ("carried", "confirm", "recorded", "never", "unclassified")})
        name = ("never" if decision.action == "never" else "recorded" if decision.action == "record"
                else "unclassified" if decision.nature == "U" else "confirm" if decision.reason == "confirm" else "carried")
        safe = safe_name(key)
        if safe not in record[name]:
            record[name].append(safe)

    def report(self) -> dict:
        roots = list(self._roots.values())
        return {"schema": 1, "roots": roots,
                "fields": [{"source": source, **{k: sorted(v) for k, v in record.items()}}
                           for source, record in sorted(self._fields.items())],
                "totals": {"files": sum(r["files"] for r in roots),
                           "carried": sum(b["carried"] for r in roots for b in r["by_nature"].values()),
                           "unclassified": sum(r["unclassified"]["count"] for r in roots),
                           "pruned_entries": sum(p["entries"] for r in roots for p in r["pruned"]),
                           "complete": all(r["complete"] for r in roots)}}


def walk_root(root: SourceRoot, *, home: Path, environ: Mapping[str, str],
              excluded: Callable[[Path], bool], ledger: Ledger, limits: Limits,
              origins: Mapping[Path, str] | None = None,
              approved_links: Mapping[Path, Path] | None = None) -> Iterator[Candidate]:
    """Enumerate/stat only; credentials and histories are never opened here."""
    base = root.resolve(home, environ)
    ledger.root(root.id, base is not None and base.exists())
    if base is None or not base.exists():
        return
    if not base.is_absolute() or not no_links(base):
        ledger.issue(root.id, "link_blocked")
        return
    count = 0

    def prune(path: Path, relative: str, rule: str, *, boundary: bool = False) -> None:
        entries = 0
        if not boundary:
            try:
                with os.scandir(path) as children:
                    entries = sum(1 for _ in children)
            except OSError:
                ledger.issue(root.id, "enumeration_failed")
        ledger.pruned(root.id, relative, rule, entries)

    def visit(path: Path, relative: str, depth: int) -> Iterator[Candidate]:
        nonlocal count
        count += 1
        if path.name.casefold() in {'.git', '.gitconfig', '.git-credentials', '.gitignore', '.gitattributes', '.gitmodules'}:
            ledger.pruned(root.id, relative, 'git_metadata_excluded', 0)
            return
        if count > limits.max_entries or depth > limits.max_depth:
            ledger.issue(root.id, "scan_limit")
            return
        if is_link(path) and approved_links and path in approved_links:
            target = approved_links[path]
            from .skills_links import link_target
            try:
                validated = link_target(home, base) if root.id == 'claude_home' and path == base/'skills' else None
            except (OSError, ValueError):
                validated = None
            if validated != (target, True) or not no_links(target) or path.resolve() != target.resolve() or not target.is_dir():
                ledger.issue(root.id, 'link_blocked')
                return
            yield from visit(target, relative, depth)
            return
        if is_link(path):
            ledger.pruned(root.id, relative, "link_blocked", 0)
            ledger.issue(root.id, "link_blocked")
            return
        scope = "project" if root.id.startswith("project:") else "agent"
        origin = next((origins[p] for p in (path, *path.parents) if p in origins), None) if origins else None
        decision = classify(root.id, relative, scope=scope, origin=origin)
        if excluded(path):
            if path.is_dir():
                prune(path, relative, "excluded_by_config", boundary=True)
            else:
                ledger.seen(root.id, relative, path.stat().st_size, Decision(None, "E", "never", "excluded_by_config"))
            return
        if path.is_dir():
            if scope == "project" and depth == 0 and path.name not in {".claude", ".codex", ".agents", ".workbuddy", ".workbuddy-ai"}:
                prune(path, relative, "PJ-07", boundary=True)
                return
            # Trailing ** can match the directory itself. Other trees remain
            # observable, including unknown files newly introduced by upgrades.
            if decision.nature in {"D", "E", "F"}:
                prune(path, relative, decision.rule_id or "boundary", boundary=decision.nature == "F")
                return
            try:
                with os.scandir(path) as children:
                    paths = sorted((Path(entry.path) for entry in children), key=lambda p: p.name)
                for child in paths:
                    if count >= limits.max_entries:
                        ledger.issue(root.id, "scan_limit")
                        break
                    yield from visit(child, relative + "/" + child.name, depth + 1)
            except OSError:
                ledger.issue(root.id, "enumeration_failed")
            return
        if not path.is_file():
            ledger.issue(root.id, "unsupported_entry")
            return
        size = path.stat().st_size
        ledger.seen(root.id, relative, size, decision)
        if decision.action in {"carry", "fields", "opt_in"} and size <= limits.max_file_bytes:
            from .catalog import CATALOG
            item = next((item for item in CATALOG if item.rule_id == decision.rule_id), None)
            if (decision.action != "opt_in" or limits.groups is not None and "history" in limits.groups):
                if limits.groups is None or item is not None and item.group in limits.groups:
                    yield Candidate(root, path, relative, size, decision)

    try:
        if excluded(base):
            ledger.issue(root.id, "excluded_by_config")
            return
        if base.is_file():
            yield from visit(base, base.name, 0)
        else:
            with os.scandir(base) as children:
                paths = sorted((Path(entry.path) for entry in children), key=lambda p: p.name)
            for path in paths:
                if count >= limits.max_entries:
                    ledger.issue(root.id, "scan_limit")
                    break
                yield from visit(path, path.name, 0)
    except OSError:
        ledger.issue(root.id, "enumeration_failed")
