"""Small injectable interaction primitives for the Chinese beginner guides."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
import sys
from typing import Callable, Sequence
import uuid


AGENT_LABELS = {"claude": "Claude", "codex": "Codex", "workbuddy": "WorkBuddy", "workbuddy-ai": "WorkBuddy AI"}
KIND_LABELS = {"rules": "规则", "settings_fields": "设置", "permissions_local": "已批准的操作",
               "persona": "人设", "skills_text": "技能", "memory": "记忆", "trust_fields": "信任的文件夹"}
REASON_LABELS = {"secret_hit": "可能含密码或私人信息", "non_text": "不是文本", "too_large": "文件过大",
                 "excluded_by_config":"按你的选择排除"}
_ENGLISH = re.compile(r"(?i)(?<![A-Za-z0-9_])(?:bundle|agent|instance|profile|preflight|dry-run|apply|undo|rules|settings_fields|permissions_local|persona|skills_text|memory|trust|trust_fields|orphan|dead_path|root-map|project_id|content_id|sha256|manifest|schema|tier|journal|state|store)(?![A-Za-z0-9_])")
_CHINESE = ("迁移包", "预检", "预览", "孤儿", "映射", "设备 ID", "档", "事务")


def forbidden_words(text: str) -> list[str]:
    """Scan guide-authored prose; callers keep original user paths separate."""
    return sorted({match.group() for match in _ENGLISH.finditer(text)} | {word for word in _CHINESE if word in text})


def clean_dragged_path(text: str) -> Path:
    value = text.strip()
    if value.startswith("& "):
        value = value[2:].strip()
    while len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    value = value.replace("\\ ", " ")
    if not value:
        raise ValueError("empty path")
    return Path(value).expanduser()


def windows_desktop() -> Path | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    initialized = ole.CoInitializeEx(None, 0)
    pointer = ctypes.c_wchar_p()
    folder_id = GUID.from_buffer_copy(uuid.UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641").bytes_le)
    try:
        status = shell.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(pointer))
        return Path(pointer.value) if status == 0 and pointer.value else None
    finally:
        if pointer:
            ole.CoTaskMemFree(ctypes.cast(pointer, ctypes.c_void_p))
        if initialized in {0, 1}:
            ole.CoUninitialize()


def desktop_path(home: Path, *, known_folder: Callable[[], Path | None] = windows_desktop) -> Path:
    try:
        known = known_folder()
    except (OSError, ValueError, AttributeError):
        known = None
    for candidate in (known, home / "Desktop", home):
        if candidate is not None and candidate.is_dir() and not candidate.is_symlink():
            return candidate
    raise ValueError("no existing save directory")


def local_time(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


class Cancelled(Exception):
    pass


@dataclass
class GuideIO:
    read: Callable[[str], str] = input
    write: Callable[[str], None] = print
    authored: list[str] = field(default_factory=list)

    def say(self, text: str) -> None:
        if forbidden_words(text):
            raise ValueError("guide prose contains internal terminology")
        self.authored.append(text)
        self.write(text)

    def data(self, text: str) -> None:
        self.write(text)

    def ask(self, text: str) -> str:
        self.say(text)
        try:
            answer = self.read("> ").strip()
        except (EOFError, KeyboardInterrupt):
            raise Cancelled from None
        if answer.casefold() == "q":
            raise Cancelled
        return answer

    def choose(self, question: str, choices: Sequence[str], *, paths: bool = False) -> list[int]:
        selected = set(range(len(choices)))
        while True:
            for index, label in enumerate(choices):
                line = f"{index + 1}. {'[已选]' if index in selected else '[未选]'} {label}"
                (self.data if paths else self.say)(line)
            answer = self.ask(question + "（回车保留当前选择；输入编号切换选择；q 退出）")
            if not answer:
                return sorted(selected)
            parts = re.split(r"[，,\s]+", answer)
            if any(not part.isdigit() or not 1 <= int(part) <= len(choices) for part in parts):
                self.say("请输入上面显示的编号，或直接按回车。")
                continue
            for part in set(parts):
                index = int(part) - 1
                selected.symmetric_difference_update({index})

    def finish(self, *, code: str | None = None) -> None:
        self.say("按回车关闭窗口。")
        if code is not None:
            self.say("错误码：" + code)
        try:
            self.read("> ")
        except (EOFError, KeyboardInterrupt, StopIteration):
            pass
