"""Standard-library bootstrap for the beginner entry points."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Sequence


def bootstrap(arguments: Sequence[str], *, root: Path | None = None, python: str | None = None,
              version: tuple[int, ...] | None = None, run: Callable = subprocess.run,
              write: Callable[[str], None] = print, os_name: str = os.name) -> int:
    project = root or Path(__file__).resolve().parents[1]
    interpreter = python or sys.executable
    current = version or tuple(sys.version_info[:3])

    def fail(what: str, next_step: str) -> int:
        write(what)
        write("原有数据：助手文件与系统设置均保留。")
        write("下一步：" + next_step)
        return 2

    if not interpreter:
        return fail("没有找到 Python。", "安装 Python 3.11 或更高版本，再双击备份。")
    if current < (3, 11):
        return fail("Python 版本太低。", "安装 Python 3.11 或更高版本，再双击备份。")
    environment = {**os.environ, "PYTHONUTF8": "1"}

    def invoke(command: list[str], *, quiet: bool = True) -> bool:
        result = run(command, cwd=project, env=environment,
                     **({"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL} if quiet else {}))
        return result.returncode == 0

    try:
        virtual = project / ".venv"
        executable = virtual / ("Scripts/python.exe" if os_name == "nt" else "bin/python")
        if virtual.is_symlink():
            return fail("运行环境的位置不安全。", "请让技术支持检查仓库内的 .venv 文件夹。")
        if not executable.is_file():
            write("首次使用，正在准备运行环境，请稍候。")
            if not invoke([interpreter, "-m", "venv", str(virtual)]) or not executable.is_file():
                return fail("运行环境没有准备成功。", "确认这个文件夹可以写入后重试。")
        if not invoke([str(executable), "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"]):
            return fail("仓库内的 Python 无法使用或版本太低。", "请让技术支持检查 .venv，使用 Python 3.11 或更高版本。")
        requirements = project / "requirements.txt"
        stamp = virtual / ".requirements.sha256"
        digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
        recorded = stamp.read_text(encoding="utf-8-sig").strip().casefold() if stamp.is_file() else ""
        if digest.casefold() != recorded:
            write("正在准备所需组件，首次使用需要联网，请稍候。")
            if not invoke([str(executable), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                           "-r", str(requirements)]):
                return fail("所需组件没有安装成功。", "检查网络连接后重试；有代理时请让技术支持配置。")
            stamp.write_text(digest, encoding="utf-8")
        entry = project / "scripts" / "machine.py"
        if not entry.is_file():
            return fail("备份程序不完整。", "重新取得完整的 ai-config 文件夹后重试。")
        result = run([str(executable), "-X", "utf8", "-B", str(entry), *arguments], cwd=project, env=environment)
        return result.returncode
    except (OSError, ValueError):
        return fail("无法准备或启动备份程序。", "确认文件夹完整、可以写入，并已安装 Python 3.11 或更高版本。")


if __name__ == "__main__":
    raise SystemExit(bootstrap(sys.argv[1:]))
