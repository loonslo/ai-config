"""Native Python 3.14 sidecar build for macOS; never packages user runtime data."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, choices=["aarch64-apple-darwin", "x86_64-apple-darwin"])
    args = parser.parse_args()
    import platform
    machine = "aarch64" if platform.machine() == "arm64" else platform.machine()
    if sys.platform != "darwin" or sys.version_info[:2] != (3, 14) or not args.target.startswith(machine + "-"):
        raise SystemExit("Build on the matching real macOS architecture with Python 3.14")
    root = Path(__file__).resolve().parents[1]
    desktop = root / "desktop"
    args_list = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--onefile", "--console", "--name", "ai-config-rpc-" + args.target,
                 "--distpath", str(desktop / "src-tauri/binaries"), "--workpath", str(desktop / ".build"), "--specpath", str(desktop / ".build"), "--paths", str(root)]
    for path in ("common", "templates", "schemas", "codex/config.toml", "claude/settings.shared.json"):
        target = str(Path(path).parent) if Path(path).suffix else path
        args_list += ["--add-data", str(root / path) + ":" + target]
    for package in ("tomlkit", "cryptography"):
        args_list += ["--collect-all", package]
    args_list += ["--hidden-import", "keyring.backends.macOS", "--copy-metadata", "keyring", "--exclude-module", "keyring.testing", "--exclude-module", "pytest"]
    args_list += [str(root / "scripts/desktop_rpc.py")]
    subprocess.run(args_list, cwd=root, check=True)


if __name__ == "__main__":
    main()
