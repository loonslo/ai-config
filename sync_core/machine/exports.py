"""Produce report-folder artifacts; never execute scripts or import accounts."""
from __future__ import annotations

import io
import json
import re
import zipfile

from .bundle import BundleError, MAX_TOTAL_BYTES
from .privacy import private_text, secret_name


def account_member(archive: str) -> tuple[str | None, str, str]:
    """Keep older single-account entries readable; new accounts have stable aliases."""
    prefix = 'files/claude/desktop/'
    if not archive.startswith(prefix):
        raise BundleError('invalid account skill export')
    parts = archive[len(prefix):].split('/')
    account = None
    if len(parts) >= 5 and parts[0] == 'accounts' and re.fullmatch(r'a[0-9]{4}', parts[1]) and parts[2] == 'skills':
        account, parts = parts[1], parts[2:]
    if len(parts) < 3 or parts[0] != 'skills':
        raise BundleError('invalid account skill export')
    return account, parts[1], '/'.join(parts[1:])


def account_skill_zip(items: list) -> bytes:
    output = io.BytesIO()
    total = 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        names = set()
        for item in sorted(items, key=lambda i: i.entry['archive_path']):
            _, _, name = account_member(item.entry['archive_path'])
            if name in names:
                raise BundleError('duplicate account skill export member')
            names.add(name)
            total += len(item.data)
            if total > MAX_TOTAL_BYTES:
                raise BundleError('account export exceeds size limit')
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, item.data)
    return output.getvalue()


def environment_script(data: bytes) -> tuple[bytes, bytes]:
    raw = json.loads(data)
    fields = raw.get('fields') if isinstance(raw, dict) else None
    if not isinstance(fields, dict):
        raise BundleError('invalid environment export')
    lines = ["# 核对后手动运行此脚本；它只设置用户级环境变量。", "$ErrorActionPreference = 'Stop'"]
    names = []
    for name, value in sorted(fields.items()):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            raise BundleError('invalid environment variable name')
        if not isinstance(value, str) or '\x00' in value or secret_name(name) or private_text(value):
            raise BundleError('credential or invalid value in environment export')
        escaped = value.replace("'", "''")
        lines.append(f"[System.Environment]::SetEnvironmentVariable('{name}', '{escaped}', 'User')")
        names.append(name)
    return (('\n'.join(lines) + '\n').encode('utf-8-sig'),
            ('# 环境变量清单\n\n请核对后自行运行同目录脚本；本工具未写入注册表。\n\n' +
             '\n'.join('- ' + name for name in names) + '\n').encode('utf-8'))
