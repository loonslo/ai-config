import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("start_bootstrap", Path(__file__).resolve().parents[1] / "scripts/start.py")
start = importlib.util.module_from_spec(spec)
spec.loader.exec_module(start)


def _project(tmp_path):
    root = tmp_path / "中文 folder"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts/machine.py").write_text("", encoding="utf-8")
    (root / "requirements.txt").write_text("tomlkit==0.13.3\n", encoding="utf-8")
    return root


def test_ready_environment_does_not_reinstall_and_preserves_arguments(tmp_path):
    root = _project(tmp_path)
    virtual = root / ".venv/Scripts"
    virtual.mkdir(parents=True)
    (virtual / "python.exe").touch()
    digest = hashlib.sha256((root / "requirements.txt").read_bytes()).hexdigest()
    (root / ".venv/.requirements.sha256").write_text(digest.upper(), encoding="utf-8")
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)
    args = ["guide", "backup", "含空格 参数"]
    assert start.bootstrap(args, root=root, python="fake", version=(3, 14), run=run) == 0
    assert len(calls) == 2
    assert calls[-1][0][-3:] == args
    assert all(kwargs['cwd'] == root for _, kwargs in calls)
    assert all(kwargs['env']['PYTHONUTF8'] == '1' for _, kwargs in calls)


@pytest.mark.parametrize('failure', ['missing', 'old', 'create', 'install'])
def test_bootstrap_failures_are_actionable_and_do_not_stamp(tmp_path, failure):
    root = _project(tmp_path)
    screen = []
    def run(command, **kwargs):
        if failure == 'missing':
            raise FileNotFoundError
        if 'venv' in command:
            if failure == 'create':
                return SimpleNamespace(returncode=1)
            executable = root / '.venv/Scripts/python.exe'
            executable.parent.mkdir(parents=True)
            executable.touch()
        if 'pip' in command and failure == 'install':
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)
    assert start.bootstrap(['guide','backup'], root=root, python='fake',
                           version=(3, 10) if failure == 'old' else (3, 14), run=run, write=screen.append) == 2
    assert any('原有数据' in line for line in screen)
    assert any('下一步' in line for line in screen)
    assert not (root / '.venv/.requirements.sha256').exists()


def test_install_success_writes_stamp_after_install_only(tmp_path):
    root = _project(tmp_path)
    stamp = root / '.venv/.requirements.sha256'
    def run(command, **kwargs):
        if 'venv' in command:
            executable = root / '.venv/Scripts/python.exe'
            executable.parent.mkdir(parents=True)
            executable.touch()
        if 'pip' in command:
            assert not stamp.exists()
        return SimpleNamespace(returncode=0)
    assert start.bootstrap(['guide','backup'], root=root, python='fake', version=(3,14), run=run) == 0
    assert stamp.read_text() == hashlib.sha256((root / 'requirements.txt').read_bytes()).hexdigest()
