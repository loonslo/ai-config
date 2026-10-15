"""Portable field selection, separate from credential processing and writes."""
from __future__ import annotations

import re
from typing import Any

from .privacy import secret_name

_ENV = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,100}')
_DEVICE = re.compile(r'DEVICE|INSTALLATION|CLIENT_HASH|CLIENT_ID|SESSION_ID|CAP_SID', re.I)
CLAUDE_CONFIRM_EXTRA = ('permissions', 'hooks', 'statusLine', 'mcpServers', 'outputStyle')


def safe_environment(raw: Any, *, portable: bool = True) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not _ENV.fullmatch(name) or secret_name(name):
            continue
        if not isinstance(value, str) or '\x00' in value:
            continue
        if portable and (_DEVICE.search(name) or re.match(r'^(?:[A-Za-z]:[\\/]|/(?:Users|home|workspace)/)', value)):
            continue
        result[name] = value
    return result


def clean_mcp_servers(raw: Any) -> dict[str, dict]:
    """Keep declared connection fields; all command-bearing fields need confirmation."""
    if not isinstance(raw, dict):
        return {}
    result = {}
    for name, server in raw.items():
        if not isinstance(name, str) or '.' in name or not isinstance(server, dict):
            continue
        selected = {key: value for key, value in server.items() if key in {'url', 'command', 'args', 'type'}}
        env = safe_environment(server.get('env'))
        if env:
            selected['env'] = env
        if selected:
            result[name] = selected
    return result


def field_names(raw: dict, prefix: str = '') -> list[str]:
    result = []
    for name, value in raw.items():
        if not isinstance(name, str) or '.' in name:
            raise ValueError('unsupported setting key')
        key = prefix + '.' + name if prefix else name
        result.extend(field_names(value, key) if isinstance(value, dict) else [key])
    return result


def mcp_field(key: str) -> bool:
    """Only declared connection leaves, rather than an arbitrary server subtree."""
    parts = key.split('.')
    if len(parts) < 3 or parts[0] != 'mcpServers' or not parts[1]:
        return False
    if len(parts)==3:
        return parts[2] in {'url','command','args','type'}
    return len(parts)==4 and parts[2]=='env' and bool(_ENV.fullmatch(parts[3])) and not secret_name(parts[3])
