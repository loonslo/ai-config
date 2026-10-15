"""External probes must finish while the desktop request pipe stays open."""
from pathlib import Path
import json
import os
import subprocess
import sys

import pytest

from sync_core.machine.bundle import BundleWriter


@pytest.mark.parametrize('legacy_encoding', ['cp1252', 'cp936'])
def test_desktop_reads_utf8_backup_path_with_legacy_pipe_encoding(tmp_path, legacy_encoding):
    archive = tmp_path / '中文备份.zip'
    writer = BundleWriter(archive, source={'os': 'windows'})
    writer.add_report('summary.md', '备份完成。')
    writer.finalize()
    home = tmp_path / 'home'
    home.mkdir()
    env = dict(os.environ, PYTHONUTF8='0', PYTHONIOENCODING=legacy_encoding,
               HOME=str(home), USERPROFILE=str(home), AI_CONFIG_HOME=str(tmp_path / 'state'),
               CODEX_HOME=str(home / '.codex'), CLAUDE_CONFIG_DIR=str(home / '.claude'))
    request = {'protocol_version': 1, 'request_id': 'unicode', 'type': 'preview',
               'operation': 'machine_restore', 'params': {'bundle': str(archive)}}
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / 'scripts/desktop_rpc.py'),
                             '--local', str(tmp_path / 'device.json')],
                            input=(json.dumps(request, ensure_ascii=False) + '\n').encode('utf-8'),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=root, env=env,
                            timeout=20, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')
    responses = [json.loads(line) for line in result.stdout.decode('utf-8').splitlines()]
    response = next(item for item in responses if item.get('type') == 'result')
    assert response['status'] == 'preview', response
    assert not result.stderr


def test_git_probes_with_live_desktop_stdin(tmp_path):
    code = '''
import sys
from pathlib import Path
from sync_core.machine.paths import git_root
from sync_core.machine.collect_login import _git_credential_keys
from sync_core.machine.collect_records import run_version_command
git_root(Path(sys.argv[1]))
_git_credential_keys()
assert run_version_command(('git', '--version'))[0] == 0
print('probes finished', flush=True)
'''
    process = subprocess.Popen([sys.executable, '-c', code, str(tmp_path)],
                               cwd=Path(__file__).resolve().parents[1],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        # Do not communicate(): it closes stdin and masks the inherited-pipe bug.
        assert process.wait(timeout=20) == 0
        assert process.stdout.readline().strip() == 'probes finished'
        assert not process.stderr.read()
    finally:
        if process.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
            else:
                process.kill()
            process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
