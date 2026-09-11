"""Small cross-platform helpers shared by the synchronization layers."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from typing import Any


SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?i:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[\"'][^\"']{12,}[\"']|"
    r"(?im:^[A-Z0-9_]*(?:PASSWORD|PASSWD|TOKEN|API_KEY)\s*=\s*\S+)"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(data: bytes | None) -> str | None:
    return sha256(data) if data is not None else None


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    """Write a file atomically on the same filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def canonical_path(value: str) -> str:
    """Canonical comparison form for Windows/macOS file name checks."""
    return "/".join(nfc(part).casefold() for part in value.replace("\\", "/").split("/"))


def safe_relative(value: str) -> str:
    # Keep the source spelling; NFC is used for collision comparison, not for
    # an implicit rename on filesystems that preserve decomposed names.
    normalized = value.replace("\\", "/")
    path = Path(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts or "\x00" in normalized:
        raise ValueError(f"Unsafe relative path: {value}")
    if any(part in {"", "."} for part in path.parts):
        raise ValueError(f"Unsafe relative path: {value}")
    return "/".join(path.parts)


def read_bytes(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ValueError(f"Symlink requires manual migration: {path}")
    return path.read_bytes() if path.exists() else None


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True
