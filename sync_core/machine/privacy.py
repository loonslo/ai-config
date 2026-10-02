"""Migration output checks; never include matched values in diagnostics."""
from __future__ import annotations

import json
import re
from typing import Any

from sync_core.utils import SECRET


# Deliberately conservative: example addresses and email-shaped identifiers also
# require exclusion under the migration checklist's output rule.
EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
URL_USERINFO = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/]+@", re.I)
_UNICODE_ESCAPE = re.compile(r'\\+u([0-9a-fA-F]{4})')


def personal_text(value: str | bytes) -> bool:
    text = value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value
    # Check escaped spellings too; this only affects detection, never source bytes.
    text = _UNICODE_ESCAPE.sub(lambda match: chr(int(match[1], 16)), text)
    return bool(EMAIL.search(text) or URL_USERINFO.search(text))


def private_text(value: str | bytes) -> bool:
    text = value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value
    if personal_text(text) or SECRET.search(text):
        return True
    if text.lstrip().startswith(('{', '[')):
        try:
            decoded = json.dumps(json.loads(text), ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError, RecursionError):
            return False
        return personal_text(decoded) or bool(SECRET.search(decoded))
    return False


def private_metadata(value: Any) -> bool:
    # ensure_ascii=False also checks non-ASCII surrounding text and JSON escapes
    # cannot conceal an address split across serialized characters.
    return private_text(json.dumps(value, ensure_ascii=False, allow_nan=False))
