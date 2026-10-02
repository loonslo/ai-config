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
from sync_core.machine.preflight import preflight
from sync_core.machine.paths import RootMap
from sync_core.machine.collect_records import software_inventory
from sync_core.machine.backup import validate_output, agent_roots
from sync_core.layout import default_state_path
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
    check = sub.add_parser("preflight", help="check a backup against this computer")
    check.add_argument("--bundle", type=Path, required=True)
    check.add_argument("--config", type=Path)
    check.add_argument("--root-map", nargs="*", default=[])
    check.add_argument("--agents")
    check.add_argument("--out-dir", type=Path)
    check.add_argument("--json", action="store_true")
    restore = sub.add_parser("restore", help="preview or restore approved backup files")
    restore.add_argument("--bundle", type=Path, required=True)
    restore.add_argument("--config", type=Path)
    restore.add_argument("--root-map", nargs="*", default=[])
    restore.add_argument("--agents")
    restore.add_argument("--json", action="store_true")
    restore.add_argument("--apply", action="store_true")
    restore.add_argument("--overwrite", nargs="*", type=Path, default=[])
    restore.add_argument("--prefer-bundle", nargs="*", default=[])
    restore.add_argument("--confirm-security", action="store_true")
    restore.add_argument("--codex-trust", action="store_true")
    restore.add_argument("--confirm-trust")
    restore.add_argument("--workbuddy-files", action="store_true", help="explicitly copy approved manual WorkBuddy texts")
    verify = sub.add_parser("verify", help="check restored file hashes and selected settings")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--config", type=Path)
    verify.add_argument("--root-map", nargs="*", default=[])
    verify.add_argument("--agents")
    verify.add_argument("--json", action="store_true")
    verify.add_argument("--reinstall-done", action="store_true", help="record your completed reinstall checklist")
    undo = sub.add_parser("undo", help="preview or undo a machine restore")
    selection = undo.add_mutually_exclusive_group()
    selection.add_argument("--index", type=int)
    selection.add_argument("--operation-id")
    undo.add_argument("--apply", action="store_true")
    undo.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "guide":
        return guide_backup()
    if args.command == "undo":
        try:
            from sync_core.machine.undo import operations, undo as undo_machine
            state = default_state_path()
            if args.index is None and args.operation_id is None:
                choices = operations(state)
                print(json.dumps(choices, ensure_ascii=False) if args.json else
                      "\n".join(f"{index}. {item['created_at']}，涉及 {item['change_count']} 个文件。" for index,item in enumerate(choices,1)))
                return 2 if choices else 0
            config = load_config()
            report = undo_machine(state, index=args.index, operation_id=args.operation_id, apply=args.apply,
                                  process_names=config.running_process_names)
            print(json.dumps(report, ensure_ascii=False) if args.json else
                  f"{'已撤销' if args.apply else '将撤销'} {report['writes']} 个文件；后续修改会受到保护。")
            return 0 if args.apply or not report['writes'] else 3
        except (OSError, ValueError, RuntimeError):
            return _failure("E7412", "无法安全撤销这次恢复。", "核对文件是否有后续修改，并关闭助手后重试。", as_json=args.json)
    if args.command in {"preflight", "restore", "verify"}:
        try:
            from sync_core.machine.bundle import validate_bundle
            import platform
            home = Path.home()
            system = platform.system().lower()
            config = load_config(args.config, home=home, target_os=system)
            selected = frozenset(name.strip() for name in args.agents.split(",")) if args.agents is not None else None
            mappings = []
            for item in args.root_map:
                old, separator, new = item.partition("=")
                if not separator or not old or not new:
                    raise ValueError("invalid root map")
                mappings.append((old, new))
            source = validate_bundle(args.bundle)["source"]["os"]
            mapper = RootMap(tuple(mappings) + config.root_map.rules, source, system)
            software = software_inventory(home=home)
            result = preflight(args.bundle, home=home, config=config, agents=selected,
                               root_map=mapper, software=software)
            if args.command == "verify":
                from sync_core.machine.verify import verify as verify_machine
                verification = verify_machine(result, software=software, reinstall_done=args.reinstall_done)
                print(json.dumps(verification.report(), ensure_ascii=False) if args.json else verification.markdown())
                return verification.exit_code
            if args.command == "restore":
                from sync_core.machine.apply import plan_restore, apply_restore
                plan = plan_restore(result, state=default_state_path(home=home),
                                    process_names=config.running_process_names, overwrite=args.overwrite,
                                    prefer_bundle=args.prefer_bundle, confirm_security=args.confirm_security,
                                    codex_trust=args.codex_trust, confirm_trust=args.confirm_trust,
                                    workbuddy_files=args.workbuddy_files)
                report = apply_restore(plan) if args.apply else plan.report()
                print(json.dumps(report, ensure_ascii=False, sort_keys=True) if args.json else
                      f"{'已处理' if args.apply else '检查完成'}：新增或调整 {report['writes']} 个文件，内容不同 {len(report['conflicts'])} 项，跳过 {len(report['skipped'])} 项。原有版本按冲突选择保留，写入前均有备份。")
                return 4 if report['conflicts'] or report['skipped'] or result.running else 3 if not args.apply and plan.changes else 0
            if args.out_dir is not None:
                output = validate_output(args.out_dir, roots=tuple(agent_roots(home, config, os.environ).values()),
                                         projects=tuple(path for path in result.projects.values() if path is not None))
                for name, text in (("preflight-report.md", result.markdown()), ("todo.md", result.todo())):
                    with (output / name).open("x", encoding="utf-8") as handle:
                        handle.write(text)
            print(json.dumps(result.report(), ensure_ascii=False, sort_keys=True) if args.json else result.markdown())
            counts = result.report()["counts"]
            return 4 if result.running or counts.get("differs") or counts.get("blocked") or result.security_list or result.trust_list else 3 if counts.get("new") else 0
        except (OSError, ValueError, KeyError, TypeError):
            return _failure("E7410", "无法安全完成恢复前检查。", "核对备份文件、工作文件夹位置和助手安装情况后重试。", as_json=args.json)
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
