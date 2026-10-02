"""Expert entry point for the offline machine kit (features added by phase)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sync_core.machine.paths import derive_project_dir


def check_claude_project_dirs(*, home: Path, claude_root: Path | None = None) -> dict[str, int]:
    """Read only project path keys; never retain or print account fields."""
    state = home / ".claude.json"
    root = claude_root or Path(os.environ.get("CLAUDE_CONFIG_DIR", str(home / ".claude")))
    with state.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    projects = raw.get("projects", {}) if isinstance(raw, dict) else {}
    keys = tuple(projects) if isinstance(projects, dict) else ()
    del projects, raw
    expected: set[str] = set()
    unsupported = 0
    for key in keys:
        name = derive_project_dir(key)
        if name is None:
            unsupported += 1
            continue
        expected.add(name)
    project_root = root / "projects"
    if project_root.is_symlink():
        raise ValueError("Claude projects directory is a symbolic link")
    actual = {directory.name for directory in project_root.iterdir()
              if directory.is_dir() and not directory.is_symlink() and any(directory.glob("*.jsonl"))} if project_root.is_dir() else set()
    return {"project_keys": len(keys), "observed_transcript_dirs": len(actual),
            "matching_dirs": len(actual & expected), "unmatched_transcript_dirs": len(actual - expected),
            "unsupported_long_paths": unsupported}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="machine")
    sub = parser.add_subparsers(dest="command", required=True)
    paths = sub.add_parser("paths", help="read-only Claude path encoding check")
    paths.add_argument("--self-check", action="store_true", required=True)
    args = parser.parse_args(argv)
    if args.command == "paths":
        try:
            report = check_claude_project_dirs(home=Path.home())
        except (OSError, ValueError, json.JSONDecodeError):
            print("无法核对路径：本机项目登记无法安全读取；没有改动任何文件。", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
