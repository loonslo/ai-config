"""Expert entry point for the offline machine kit (features added by phase)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sync_core.machine.paths import derive_project_dir
from sync_core.machine.backup import AGENTS, apply_backup, prepare_backup
from sync_core.machine.config import load_config
from sync_core.machine.guide_backup import guide_backup
from sync_core.messages import Message


def _failure(code: str, what: str, next_step: str, *, as_json: bool, exit_code: int = 1) -> int:
    message = Message(code, what, "本机助手文件未被改写；已存在的备份保留。", next_step, exit_code=exit_code)
    print(json.dumps(message.as_json(), ensure_ascii=False) if as_json else "\n".join(message.lines()), file=sys.stderr)
    return exit_code


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
    backup = sub.add_parser("backup", help="preview or create an offline machine bundle")
    backup.add_argument("--config", type=Path)
    backup.add_argument("--out", type=Path)
    backup.add_argument("--name", default="machine-bundle")
    backup.add_argument("--agents", help="comma-separated agent names")
    backup.add_argument("--apply", action="store_true")
    backup.add_argument("--json", action="store_true")
    guide = sub.add_parser("guide", help="beginner interactive guide")
    guide.add_argument("operation", choices=("backup",))
    args = parser.parse_args(argv)
    if args.command == "guide":
        return guide_backup()
    if args.command == "paths":
        try:
            report = check_claude_project_dirs(home=Path.home())
        except (OSError, ValueError, json.JSONDecodeError):
            print("无法核对路径：本机项目登记无法安全读取；没有改动任何文件。", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "backup":
        if args.apply and args.out is None:
            return _failure("E7401", "写入备份需要指定保存目录。", "增加 --out <已存在的目录> 后重试。", as_json=args.json, exit_code=2)
        home = Path.home()
        selected = frozenset(name.strip() for name in args.agents.split(",")) if args.agents is not None else None
        if selected is not None and (not selected or selected - AGENTS):
            return _failure("E7402", "助手列表无法识别。", "从 claude、codex、workbuddy、workbuddy-ai 中选择，用逗号分隔。", as_json=args.json, exit_code=2)
        out = args.out or (home / "Desktop" if (home / "Desktop").is_dir() else home)
        try:
            config = load_config(args.config, home=home)
            plan = prepare_backup(home=home, config=config, out=out, name=args.name, agents=selected)
            report = apply_backup(plan) if args.apply else plan.preview()
        except (OSError, ValueError):
            return _failure("E7403", "无法安全完成备份采集或发布。", "核对配置、保存目录和源文件；关闭正在修改配置的助手后重试。", as_json=args.json)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            print(f"{'备份已保存' if args.apply else '备份预览'}：{report['destination']}")
            print(f"条目 {report['entries']}；项目 {report['projects']}；排除 {len(report['exclusions'])}；提醒 {len(report['warnings'])}。")
            for item in report["exclusions"]:
                print(f"未备份 {item['reason']}：{item['logical_path']}")
            if args.apply:
                print(f"SHA-256：{report['sha256']}")
            else:
                print("核对后增加 --apply 并指定 --out 保存备份。")
        return 0 if args.apply else 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
