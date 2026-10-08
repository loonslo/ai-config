"""Read-only software inventory for the reinstall report."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
from typing import Callable

from .config import DEFAULT_PROCESSES

Run = Callable[[tuple[str, ...]], tuple[int, str]]
_VERSION = re.compile(r"\d+(?:\.\d+)+(?:[-+][A-Za-z0-9.]+)?")


def run_version_command(command: tuple[str, ...]) -> tuple[int, str]:
    """Never use a shell or network; bound time and retained output."""
    try:
        program = shutil.which(command[0])
        if program is None:
            return 1, ""
        result = subprocess.run((program, *command[1:]), capture_output=True, text=True, timeout=10, check=False,
                                stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return result.returncode, result.stdout[:1_000_000]


def symlinks_supported() -> bool:
    with tempfile.TemporaryDirectory(prefix="ai-machine-link-") as directory:
        root = Path(directory)
        target = root / "target"
        target.write_bytes(b"")
        link = root / "link"
        try:
            link.symlink_to(target)
            return link.is_symlink()
        except (OSError, NotImplementedError):
            return False


def _version(run: Run, command: tuple[str, ...]) -> str | None:
    rc, output = run(command)
    match = _VERSION.search(output[:4096]) if rc == 0 else None
    return match.group(0) if match else None


def software_inventory(*, run: Run = run_version_command, link_probe: Callable[[], bool] = symlinks_supported,
                       process_names: tuple[str, ...] = DEFAULT_PROCESSES,
                       claude_code_dir: Path | None = None, home: Path | None = None) -> dict[str, object]:
    """Return only version numbers, package names and availability facts."""
    commands: dict[str, tuple[str, ...]] = {
        "node": ("node", "--version"), "npm": ("npm", "--version"),
        "python": ("python", "--version"), "git": ("git", "--version"),
        "git_lfs": ("git", "lfs", "version"), "uv": ("uv", "--version"),
        "pnpm": ("pnpm", "--version"), "cargo": ("cargo", "--version"),
        "rustc": ("rustc", "--version"), "codex_cli": ("codex", "--version"),
    }
    commands["winget" if os.name == "nt" else "brew"] = ("winget", "--version") if os.name == "nt" else ("brew", "--version")
    versions = {name: _version(run, command) for name, command in commands.items()}
    _rc, output = run(("npm", "ls", "-g", "--depth=0", "--json"))
    global_packages: dict[str, str] = {}
    if output and len(output) <= 1_000_000:
        try:
            start = output.index("{")
            parsed, _end = json.JSONDecoder().raw_decode(output[start:])
            dependencies = parsed.get("dependencies", {})
            if isinstance(dependencies, dict):
                for name, info in dependencies.items():
                    if (isinstance(name, str) and re.fullmatch(r"[@A-Za-z0-9_.\-/]{1,120}", name)
                            and isinstance(info, dict) and isinstance(info.get("version"), str)):
                        match = _VERSION.fullmatch(info["version"])
                        if match:
                            global_packages[name] = match.group(0)
        except (ValueError, AttributeError, TypeError):
            pass
    desktop_versions: list[str] = []
    if claude_code_dir is None:
        user_home = Path.home() if home is None else home
        claude_code_dir = (user_home / "AppData" / "Roaming" / "Claude" / "claude-code") if os.name == "nt" else (user_home / "Library" / "Application Support" / "Claude" / "claude-code")
    if claude_code_dir is not None and claude_code_dir.is_dir() and not claude_code_dir.is_symlink():
        desktop_versions = sorted(entry.name for entry in claude_code_dir.iterdir()
                                  if entry.is_dir() and _VERSION.fullmatch(entry.name))
    return {
        "os": platform.system().lower(), "os_version": platform.version(), "arch": platform.machine(),
        "versions": versions, "npm_global_packages": global_packages,
        "claude_desktop_claude_code_versions": desktop_versions,
        "codex_desktop_version": None, "cc_switch_version": None,
        "symlinks_supported": link_probe(), "target_process_names": list(process_names),
        "unverified": ["codex_desktop_version", "cc_switch_version"]
        + (["claude_desktop_claude_code_versions"] if not desktop_versions else []),
    }
