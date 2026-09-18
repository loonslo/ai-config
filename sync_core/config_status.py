"""Verify the real tool target files and detect configuration drift.

The source repository being consistent says nothing about what the tools
actually loaded.  This module reads the managed content out of the real target
files (``AGENTS.md``, ``CLAUDE.md``, ``config.toml``, ``settings.json``), compares
only the managed projection, and reports missing, malformed, locally modified,
pending and applied states.

Callers must re-read a target after applying and confirm the write; a failed
read-back never produces a success receipt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .config import managed_fields
from .status import STATUS_CODES
from .utils import digest

#: Managed block markers shared with the rules writer.
BEGIN = b"<!-- ai-config:begin -->"
END = b"<!-- ai-config:end -->"


class TargetUnreadable(RuntimeError):
    """The target could not be read; the state is unknown, not applied."""


def _read(path: Path) -> bytes | None:
    if path.is_symlink():
        raise TargetUnreadable(f"Symlink requires manual migration: {path}")
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except OSError as error:
        raise TargetUnreadable(f"Cannot read target file: {path}") from error


def managed_block(data: bytes | None) -> tuple[bytes | None, str | None]:
    """Extract the managed rules block, or explain why it is unusable."""
    if data is None:
        return None, "missing"
    if BEGIN not in data and END not in data:
        return None, "no_managed_block"
    if data.count(BEGIN) != 1 or data.count(END) != 1:
        return None, "malformed_managed_block"
    start, stop = data.index(BEGIN), data.index(END) + len(END)
    if start > stop:
        return None, "malformed_managed_block"
    return data[start:stop], None


def managed_rules_projection(data: bytes | None) -> str | None:
    """Digest of only the managed block; unrelated content is ignored."""
    block, error = managed_block(data)
    if error is not None:
        return None
    return digest(block)


def _toml_managed_projection(data: bytes | None, keys: tuple[str, ...]) -> tuple[str | None, str | None]:
    """Digest of the selected scalar keys only, preserving everything else."""
    if data is None:
        return None, "missing"
    if not keys:
        return None, "no_managed_fields"
    try:
        import tomlkit
        document = tomlkit.parse(data.decode("utf-8"))
    except Exception:  # noqa: BLE001 - tomlkit raises several parse errors
        return None, "malformed_target"
    present: dict[str, Any] = {}
    for key in keys:
        if key in document:
            present[key] = str(document[key])
    if not present:
        return None, "no_managed_fields"
    from .utils import json_bytes
    return digest(json_bytes(present)), None


def _json_managed_projection(data: bytes | None, keys: tuple[str, ...]) -> tuple[str | None, str | None]:
    if data is None:
        return None, "missing"
    if not keys:
        return None, "no_managed_fields"
    import json
    try:
        document = json.loads(data.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return None, "malformed_target"
    if not isinstance(document, dict):
        return None, "malformed_target"
    present = {key: document[key] for key in keys if key in document}
    if not present:
        return None, "no_managed_fields"
    from .utils import json_bytes
    return digest(json_bytes(present)), None


def scope_targets(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Describe every target file this device manages, without reading it yet."""
    from .config import absolute

    targets: list[dict[str, Any]] = []
    for tool, filename in (("codex", "AGENTS.md"), ("claude", "CLAUDE.md")):
        root = raw.get(tool)
        if not root:
            continue
        targets.append({
            "tool": tool,
            "target": str(absolute(root) / filename),
            "target_kind": "rules_block",
            "fields": ["rules"],
        })
    if raw.get("codex"):
        targets.append({
            "tool": "codex",
            "target": str(absolute(raw["codex"]) / "config.toml"),
            "target_kind": "config",
            "fields": list(managed_fields(raw).get("codex", [])),
        })
    if raw.get("claude"):
        targets.append({
            "tool": "claude",
            "target": str(absolute(raw["claude"]) / "settings.json"),
            "target_kind": "settings",
            "fields": list(managed_fields(raw).get("claude", [])),
        })
    return targets


def observed_digest(target: Mapping[str, Any], data: bytes | None) -> tuple[str | None, str | None]:
    """Digest the managed projection, or return the reason it is unknown."""
    kind = target.get("target_kind")
    if kind == "rules_block":
        # `managed_block` already distinguishes missing / no block / malformed;
        # discarding its reason would let a missing file look applied.
        block, error = managed_block(data)
        if error is not None:
            return None, error
        return digest(block), None
    if kind == "config":
        return _toml_managed_projection(data, tuple(target.get("fields", [])))
    if kind == "settings":
        return _json_managed_projection(data, tuple(target.get("fields", [])))
    return None, "unknown_target_kind"


def expected_digest(target: Mapping[str, Any], expected_projection: bytes | Mapping[str, str] | None) -> str | None:
    """Digest the projection the source would produce for this target."""
    if expected_projection is None:
        return None
    if isinstance(expected_projection, (bytes, bytearray)):
        return digest(bytes(expected_projection))
    from .utils import json_bytes
    return digest(json_bytes(dict(expected_projection)))


def inspect_target(
    target: Mapping[str, Any],
    *,
    expected_projection: bytes | Mapping[str, str] | None,
    last_applied_digest: str | None = None,
) -> dict[str, Any]:
    """Compare one real target against the projection the source produces."""
    path = Path(target["target"])
    try:
        data = _read(path)
    except TargetUnreadable as error:
        return {
            "tool": target.get("tool"),
            "target": target.get("target"),
            "target_kind": target.get("target_kind"),
            "fields": list(target.get("fields", [])),
            "status": "apply_failed",
            "expected_digest": expected_digest(target, expected_projection),
            "observed_digest": None,
            "detail": f"target cannot be read: {error}",
        }
    expected = expected_digest(target, expected_projection)
    observed, error = observed_digest(target, data)
    status, detail = _classify(expected=expected, observed=observed, error=error, last_applied=last_applied_digest)
    return {
        "tool": target.get("tool"),
        "target": target.get("target"),
        "target_kind": target.get("target_kind"),
        "fields": list(target.get("fields", [])),
        "status": status,
        "expected_digest": expected,
        "observed_digest": observed,
        "detail": detail,
    }


def _classify(*, expected: str | None, observed: str | None, error: str | None, last_applied: str | None) -> tuple[str, str | None]:
    if error == "missing":
        # A missing target is never treated as applied.
        return "not_configured", "target file is missing"
    if error == "malformed_managed_block":
        return "apply_failed", "managed block is duplicated or malformed"
    if error == "malformed_target":
        return "apply_failed", "target file is not parseable"
    if error == "no_managed_fields":
        return "pending_sync", "no managed field is present in the target yet"
    if error == "no_managed_block":
        return "pending_sync", "target has no managed block yet"
    if error is not None:
        return "apply_failed", error
    if observed is None:
        return "apply_failed", "managed projection is unreadable"
    if expected is not None and observed == expected:
        return "applied", None
    if last_applied is not None and observed == last_applied:
        # The target still matches the version we applied earlier; the source
        # has moved on, so this device is simply behind.
        return "pending_sync", "target matches the last applied version; the source has newer content"
    return "local_modified", "managed content differs from the source projection"


def ensure_status(status: str) -> str:
    if status not in STATUS_CODES:
        raise ValueError(f"Unknown target status: {status}")
    return status


def summarize(targets: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for target in targets:
        status = str(target.get("status", "not_configured"))
        counts[status] = counts.get(status, 0) + 1
    return counts
