"""Read user environment names first; never query secret-name values."""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Callable, Mapping

from .bundle import BundleWriter
from .collect_tier1 import CollectionResult
from .config import MachineConfig
from .privacy import private_text, secret_name


_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
_PREFIXES = ('ANTHROPIC_', 'CLAUDE_', 'CODEX_', 'OPENAI_', 'AI_')
_EXACT = {'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'API_TIMEOUT_MS'}


def relevant(name: str, include: frozenset[str]) -> bool:
    return bool(_NAME.fullmatch(name)) and (name.upper().startswith(_PREFIXES) or name.upper() in _EXACT or name in include)


def registry_environment(include: frozenset[str]) -> dict[str, str | None]:
    """EnumValue's value-returning API is deliberately avoided."""
    import winreg
    from ctypes import wintypes
    values: dict[str, str | None] = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_READ)
    except FileNotFoundError:
        return values
    enum = ctypes.WinDLL('advapi32', use_last_error=True).RegEnumValueW
    enum.argtypes = [wintypes.HKEY, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
                     ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    enum.restype = wintypes.LONG
    with key:
        count = winreg.QueryInfoKey(key)[1]
        for index in range(count):
            buffer = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buffer))
            code = enum(int(key), index, buffer, ctypes.byref(length), None, None, None, None)
            if code:
                raise OSError('user environment name enumeration failed')
            name = buffer.value
            if not relevant(name, include):
                values[name] = None
                continue
            if secret_name(name):
                values[name] = None
                continue
            value, kind = winreg.QueryValueEx(key, name)
            if kind in {winreg.REG_SZ, winreg.REG_EXPAND_SZ} and isinstance(value, str):
                values[name] = value
    return values


def snapshot(table: Mapping[str, str | None], include: frozenset[str]) -> tuple[dict[str, str], tuple[str, ...]]:
    safe: dict[str, str] = {}
    login: list[str] = []
    for name in sorted(table):
        if not isinstance(name, str) or not relevant(name, include):
            continue
        if secret_name(name):
            login.append(name)
            continue
        value = table[name]
        if not isinstance(value, str) or '\x00' in value:
            continue
        if private_text(value):
            login.append(name)
        else:
            safe[name] = value
    return safe, tuple(login)


@dataclass
class EnvironmentResult(CollectionResult):
    login_names: tuple[str, ...] = ()
    _check: Callable[[], bool] = field(default=lambda: True, repr=False)

    def verify_sources_unchanged(self) -> bool:
        return self._check()


def collect_environment(writer: BundleWriter, *, home: Path, config: MachineConfig, os_name: str,
                        table: Mapping[str, str | None] | None = None) -> EnvironmentResult:
    if not writer.wants('env_fields'):
        return EnvironmentResult()
    reader = (lambda: table) if table is not None else (
        (lambda: registry_environment(config.env_include)) if os_name.lower() in {'windows', 'nt', 'win32'} and home == Path.home()
        else (lambda: {}))
    initial_table = reader()
    initial = snapshot(initial_table, config.env_include)
    safe, names = initial
    result = EnvironmentResult(login_names=names, _check=lambda: snapshot(reader(), config.env_include) == initial)
    from .catalog import Decision
    for name in sorted(initial_table):
        if not relevant(name, config.env_include):
            decision = Decision('SY-03', 'E', 'never')
        elif name in names:
            decision = Decision('SY-02', 'D', 'never')
        elif name in safe:
            decision = Decision('SY-01', 'B', 'fields', 'confirm')
        else:
            decision = Decision('SY-01', 'B', 'record', 'unsupported_value')
        result.field_ledger.field('user_env', name, decision)
    if safe:
        data = (json.dumps({'fields': safe}, ensure_ascii=False, sort_keys=True) + '\n').encode()
        writer.add_file('files/system/main/env.fields.json', data, agent='system', instance='main', kind='env_fields',
                        logical_path='system:main/user-env', restore='export', mode='fields', fields=sorted(safe),
                        confirm_fields=sorted(safe), rule_id='SY-01', nature='B', group='settings')
    return result
