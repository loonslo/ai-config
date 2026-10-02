"""Canonical locations for user data, separate from the installed checkout."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
from typing import Any

from .config import load as load_config
from .utils import atomic_write


class LayoutError(RuntimeError):
    """A local data path or legacy configuration cannot be migrated safely."""


def data_root(*, home: Path | None = None, environ: dict[str, str] | None = None) -> Path:
    """Return the user data root; AI_CONFIG_HOME supports managed installations."""
    env = os.environ if environ is None else environ
    override = env.get("AI_CONFIG_HOME")
    root = Path(override).expanduser() if override else (home or Path.home()) / ".ai-sync"
    if not root.is_absolute():
        raise LayoutError("AI_CONFIG_HOME must be an absolute path.")
    root = Path(os.path.abspath(root))
    for parent in (root, *root.parents):
        if parent.is_symlink():
            raise LayoutError(f"User data root contains a symlink; choose a local data folder explicitly: {root}")
    return root


def default_store_path(*, home: Path | None = None, environ: dict[str, str] | None = None) -> Path:
    return data_root(home=home, environ=environ) / "store"


def default_state_path(*, home: Path | None = None, environ: dict[str, str] | None = None) -> Path:
    return data_root(home=home, environ=environ) / "state"


def default_device_config_path(*, home: Path | None = None, environ: dict[str, str] | None = None) -> Path:
    return data_root(home=home, environ=environ) / "device.json"


@dataclass(frozen=True)
class DeviceConfigImport:
    source: Path
    target: Path
    source_digest: str
    backup: Path
    action: str


def plan_device_config_import(source: Path, target: Path) -> DeviceConfigImport:
    """Validate an old device.json and describe a copy without writing files."""
    source = Path(os.path.abspath(Path(source).expanduser()))
    target = Path(os.path.abspath(Path(target).expanduser()))
    if any(parent.is_symlink() for path in (source, target) for parent in (path, *path.parents)):
        raise LayoutError("配置文件是符号链接；为避免写到其他位置，请先选择实际文件。")
    if not source.is_file():
        raise LayoutError(f"找不到待导入的设备配置：{source}")
    try:
        load_config(source)
    except (OSError, ValueError) as error:
        raise LayoutError(f"设备配置无法读取或不符合当前格式；未写入新文件：{error}") from error

    data = source.read_bytes()
    source_digest = hashlib.sha256(data).hexdigest()
    if source == target:
        return DeviceConfigImport(source, target, source_digest, source, "already_imported")
    if target.exists():
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == source_digest:
            return DeviceConfigImport(source, target, source_digest, source, "already_imported")
        raise LayoutError(f"目标设备配置已存在且内容不同；不会覆盖：{target}")

    backup = source.with_name(source.name + ".bak-ai-config")
    if backup.exists() and (not backup.is_file() or hashlib.sha256(backup.read_bytes()).hexdigest() != source_digest):
        raise LayoutError(f"旧配置备份位置已被其他文件占用；不会覆盖：{backup}")
    return DeviceConfigImport(source, target, source_digest, backup, "copy")


def import_device_config(plan: DeviceConfigImport) -> dict[str, Any]:
    """Copy a validated legacy file and its backup into the new user data root."""
    if plan.action == "already_imported":
        return {"status": "already_imported", "source": str(plan.source), "target": str(plan.target), "backup": None}

    # A lock also prevents two invocations from racing to create the device
    # configuration or its backup.  The plan is rechecked inside the lock.
    from .transaction import SyncLock

    root = plan.target.parent
    state_root = root / "state"
    root.mkdir(parents=True, exist_ok=True)
    with SyncLock(state_root):
        current = plan_device_config_import(plan.source, plan.target)
        if current.source_digest != plan.source_digest:
            raise LayoutError("旧配置在预览后发生变化；请重新预览迁移。")
        if current.action == "already_imported":
            return {"status": "already_imported", "source": str(plan.source), "target": str(plan.target), "backup": None}

        data = plan.source.read_bytes()
        if plan.backup.exists():
            if plan.backup.read_bytes() != data:
                raise LayoutError(f"旧配置备份在迁移期间发生变化；不会覆盖：{plan.backup}")
        else:
            try:
                with plan.backup.open("xb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError as error:
                raise LayoutError(f"旧配置备份位置在迁移期间被占用；不会覆盖：{plan.backup}") from error

        try:
            atomic_write(plan.target, data)
            load_config(plan.target)
        except (OSError, ValueError) as error:
            if plan.target.is_file() and hashlib.sha256(plan.target.read_bytes()).hexdigest() == plan.source_digest:
                plan.target.unlink()
            raise LayoutError(f"写入新设备配置失败；原文件及备份仍保留：{error}") from error

    return {
        "status": "imported",
        "source": str(plan.source),
        "target": str(plan.target),
        "backup": str(plan.backup),
    }
