"""External probes must finish while the desktop request pipe stays open."""
from pathlib import Path
import os
import subprocess
import sys


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
