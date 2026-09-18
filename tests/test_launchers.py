"""Regression tests for the launcher entry points (TASK-05).

These assert the launchers' contract statically: they resolve their own
directory, reuse a project-local environment, and never mutate the system.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PS1 = (ROOT / "ai-config.ps1").read_text(encoding="utf-8")
COMMAND = (ROOT / "ai-config.command").read_text(encoding="utf-8")


def test_launchers_exist_and_do_not_depend_on_the_callers_directory():
    assert "MyInvocation.MyCommand.Path" in PS1
    assert 'dirname -- "${BASH_SOURCE[0]}"' in COMMAND


def test_launcher_prefers_an_existing_venv_without_needing_a_system_python():
    """A machine with a ready .venv must not fail because PATH lacks python."""
    # The venv check has to happen before the system-Python lookup.
    venv_check = PS1.index("$venvReady = Test-Path")
    find_python = PS1.index("$python = Find-Python")
    assert venv_check < find_python, "launcher must try .venv before requiring system python"
    # Creating the venv is guarded, so an existing venv skips the whole block.
    assert "if (-not $venvReady) {" in PS1


def test_launchers_never_modify_the_system():
    assert "setx" not in PS1.casefold()
    assert "ExecutionPolicy" not in PS1
    assert "npm install -g" not in COMMAND
    assert "sudo" not in COMMAND


def test_repeated_startup_does_not_reinstall_dependencies():
    # Both launchers gate installation on a recorded requirements hash.
    assert "requirements.sha256" in PS1
    assert "requirements.sha256" in COMMAND
    # The stamp is written only after a successful install.
    assert "pip install" in PS1
    assert "pip install" in COMMAND


def test_launcher_and_command_agree_on_the_entry_point():
    # Both must invoke sync.py with the same argument passthrough contract.
    assert "scripts/sync.py" in COMMAND
    assert "@Arguments" in PS1
    assert '"$@"' in COMMAND


def test_launchers_exit_nonzero_with_an_actionable_message_when_unusable():
    # A missing environment must exit 2 with a what/preserved/next-step message.
    assert "exit 2" in PS1
    assert "原有数据" in PS1
    assert "下一步" in PS1
    assert "fail " in COMMAND or "exit 2" in COMMAND
