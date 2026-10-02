"""Five-screen beginner backup using the same expert backup engine."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from fnmatch import fnmatchcase
import os
from pathlib import Path
import platform
import traceback
from typing import Any, Callable, Mapping

from sync_core.layout import data_root, default_state_path
from sync_core.messages import Message

from .backup import agent_roots, apply_backup, prepare_backup, validate_output
from .collect_projects import known_folders
from .config import MachineConfig, load_config
from .guided import AGENT_LABELS, KIND_LABELS, REASON_LABELS, Cancelled, GuideIO, desktop_path, local_time
from .paths import norm


def filter_folders(paths: list[str], *, home: Path, patterns: tuple[str, ...], os_name: str) -> tuple[Path, ...]:
    found: dict[str, Path] = {}
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute() or not path.is_dir() or path.is_symlink():
            continue
        if norm(path, os_name).casefold() == norm(home, os_name).casefold():
            continue
        names = [norm(path, os_name)]
        if path.is_relative_to(home):
            names.append(path.relative_to(home).as_posix())
        compare = [value.casefold() if os_name == "windows" else value for value in names]
        excludes = [pattern.casefold() if os_name == "windows" else pattern for pattern in patterns]
        if any(fnmatchcase(value, pattern) or (pattern.endswith("/**") and value == pattern[:-3])
               for value in compare for pattern in excludes):
            continue
        identity = norm(path, os_name).casefold() if os_name == "windows" else norm(path, os_name)
        found.setdefault(identity, path)
    return tuple(found[key] for key in sorted(found))


def _log_failure(error: Exception, *, home: Path, env: Mapping[str, str]) -> Path | None:
    """Keep stack locations, never exception values or captured local variables."""
    try:
        root = default_state_path(home=home, environ=dict(env))
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"machine-guide-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}.log"
        frames = traceback.extract_tb(error.__traceback__)
        text = type(error).__name__ + "\n" + "\n".join(f"{frame.filename}:{frame.lineno}:{frame.name}" for frame in frames)
        with target.open("x", encoding="utf-8") as handle:
            handle.write(text + "\n")
        return target
    except (OSError, ValueError):
        return None


def guide_backup(*, io: GuideIO | None = None, home: Path | None = None,
                 config: MachineConfig | None = None, config_used: bool | None = None,
                 environ: Mapping[str, str] | None = None, os_name: str | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 desktop: Callable[[Path], Path] = desktop_path,
                 discover: Callable[..., list[str]] = known_folders,
                 software: dict[str, Any] | None = None, git_keys: list[str] | None = None) -> int:
    ui = io or GuideIO()
    user_home = home or Path.home()
    env = os.environ if environ is None else environ
    system = os_name or platform.system().lower()
    saved: Path | None = None
    try:
        ui.ask("把 AI 助手的规则、记忆和设置打包成一个文件放到桌面。原有文件会保留，也不会上传到网上。按回车继续，q 退出。")
        location = data_root(home=user_home, environ=dict(env)) / "machine.config.json"
        selected_config = config or load_config(location, home=user_home, source_os=system)
        used = location.is_file() if config_used is None else config_used
        roots = agent_roots(user_home, selected_config, env)
        detected = [name for name in AGENT_LABELS if roots[name].is_dir() and not roots[name].is_symlink()]
        for name in AGENT_LABELS:
            if name not in detected:
                ui.say(f"{AGENT_LABELS[name]}：未找到，已跳过。")
        if not detected:
            ui.say("没有找到可备份的 AI 助手。原有文件均保留；请先安装并启动助手一次，再重新打开备份。")
            ui.finish()
            return 0
        indices = ui.choose("选择要备份的 AI 助手", [AGENT_LABELS[name] for name in detected])
        agents = frozenset(detected[index] for index in indices)
        if not agents:
            raise Cancelled
        if used:
            ui.say("已使用你的配置文件。")
            projects = filter_folders([str(path) for path in selected_config.core_projects], home=user_home,
                                      patterns=selected_config.exclude_patterns, os_name=system)
        else:
            projects = filter_folders(discover(home=user_home, environ=env, os_name=system, agents=agents),
                                      home=user_home, patterns=selected_config.exclude_patterns, os_name=system)
        if projects:
            indices = ui.choose("选择工作文件夹", [str(path) for path in projects], paths=True)
            projects = tuple(projects[index] for index in indices)
        else:
            ui.say("没有找到工作文件夹，将备份已选择的助手设置与全局内容。")
        selected_config = replace(selected_config, core_projects=projects)
        output = desktop(user_home)
        try:
            validate_output(output, roots=tuple(roots.values()), projects=projects)
        except ValueError:
            ui.say("桌面位置不适合保存备份，改为保存到你的个人文件夹。")
            output = validate_output(user_home, roots=tuple(roots.values()), projects=projects)
        now = clock()
        plan = prepare_backup(home=user_home, config=selected_config, out=output, name="AI备份", agents=agents,
                              environ=env, os_name=system, now=now, software=software, git_keys=git_keys)
        ui.say("检查完成，原有文件均保留。")
        counts = Counter(entry["kind"] for entry in plan.writer.entries if entry["kind"] != "report")
        for kind, count in sorted(counts.items()):
            ui.say(f"{KIND_LABELS[kind]}：{count} 个文件。")
        ui.say(f"已批准的操作共 {plan.project_result.local_rules} 条。")
        if plan.exclusions:
            ui.say(f"有 {len(plan.exclusions)} 个文件因为可能含密码、不是文本或过大，没有放进备份。请核对位置：")
            for item in plan.exclusions:
                ui.say(REASON_LABELS.get(item["reason"], "需要人工核对"))
                ui.data(item.get("source_path", item["logical_path"]))
        for warning in plan.warnings:
            ui.say("有一项设置或文件无法读取，详细情况会保存在备份说明里。")
        ui.data(str(plan.writer.destination))
        answer = ui.ask("开始备份吗？（回车开始；q 退出）")
        if answer.casefold() not in {"", "y", "yes", "是"}:
            raise Cancelled
        report = apply_backup(plan)
        saved = plan.writer.destination
        ui.say("备份已保存，原有文件均保留。")
        ui.data(str(saved))
        ui.say(f"大小：{report['bytes'] / 1024:.1f} KB；完成时间：{local_time(clock())}。")
        ui.say("请把它复制到新电脑；文件里有你的个人记忆，请妥善保管。")
        ui.finish()
        return 0
    except Cancelled:
        ui.say("已退出，没有改动任何文件。需要备份时，可以重新打开。")
        ui.finish()
        return 0
    except Exception as error:
        log = _log_failure(error, home=user_home, env=env)
        message = Message("E7404", "本次备份未完成。", "助手原有文件均保留，已存在的备份保留。",
                          "核对保存位置，关闭正在修改助手配置的程序后重试。")
        ui.say(message.what)
        ui.say("原有数据：" + message.preserved)
        ui.say("下一步：" + message.next_step)
        if log is not None:
            ui.say("可以把以下日志位置提供给技术支持：")
            ui.data(str(log))
        if saved is not None:
            ui.data(str(saved))
        ui.finish(code=message.code)
        return 1
