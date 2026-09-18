"""Per-device receipts published to a dedicated branch.

Receipts record which managed scope a device actually selected, the content
digest and the version it verified as applied.  They are written to a separate
branch with one file per device, so updating a receipt never changes the
configuration content version on ``main`` and two devices reporting at the same
time cannot overwrite each other.

The branch lives on the *configuration source* remote.  A temporary workspace is
used for every operation, so the user's checkout is never switched, and the
remote URL is read from that checkout: pointing the workspace at the local path
would look like a successful upload while nothing ever left the machine.

All Git work happens in an isolated workspace: the user's working branch is
never switched.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping

from .status import STATUS_CODES, receipt_is_sensitive_free, shared_receipt, validate_state
from .utils import SECRET, atomic_write, json_bytes

#: The receipt branch is intentionally not ``main``.
RECEIPT_BRANCH = "device-receipts"
RECEIPT_DIR = "receipts"

_GIT_TIMEOUT = 60.0

#: A remote that asks for credentials must never block a sync.
_GIT_ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
    "GCM_INTERACTIVE": "never",
}


class ReceiptError(RuntimeError):
    """A receipt could not be written or read safely."""


class ReceiptUnavailable(ReceiptError):
    """There is no remote to report to; this is not an upload failure."""


def _git(root: Path, *args: str, check: bool = True, timeout: float = _GIT_TIMEOUT) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            env=_GIT_ENV,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise ReceiptError("Git 操作超时或无法执行，本机状态仍然保留。") from error
    if check and completed.returncode:
        # Never surface raw git stderr: it can contain credentialed URLs.
        raise ReceiptError(f"Git 操作失败（{args[0] if args else 'git'}）。")
    return completed.stdout.strip()


def _resolve_remote(root: Path, value: str) -> str:
    """Resolve a relative local-path remote against the checkout it belongs to.

    Git stores the URL exactly as configured, so ``../remote.git`` means
    "relative to this checkout".  A receipt workspace is a temporary directory
    somewhere else, where the same relative path would point at nothing — and the
    push would fail for a reason that has nothing to do with the receipt.
    """
    first = value.split("/", 1)[0]
    if "://" in value or ":" in first or value.startswith(("/", "\\\\", "~")):
        return value
    candidate = root / value
    return str(candidate.resolve()) if candidate.exists() else value


def remote_url(root: Path) -> str | None:
    """The real remote of the configuration source, never the local path."""
    if not (root / ".git").exists():
        return None
    value = _git(root, "remote", "get-url", "origin", check=False)
    if not value:
        return None
    return _resolve_remote(root, value)


def receipt_path(root: Path, device_id: str) -> Path:
    _validate_device(device_id)
    return root / RECEIPT_DIR / f"{device_id}.json"


def _validate_device(device_id: str) -> None:
    import re
    if not isinstance(device_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", device_id):
        raise ReceiptError("设备 ID 无效，无法写入回执。")


def write_receipt(root: Path, state: Mapping[str, Any]) -> dict[str, Any]:
    """Write the local device receipt and return it.

    This operates on the checked-out receipt workspace only; the caller is
    responsible for publishing it.
    """
    validate_state(state)
    receipt = shared_receipt(state)
    if not receipt_is_sensitive_free(receipt):
        raise ReceiptError("回执包含本机路径或敏感值，已拒绝写入。")
    serialized = json_bytes(receipt).decode("utf-8")
    if SECRET.search(serialized):
        raise ReceiptError("回执内容命中敏感信息规则，已拒绝写入。")
    target = receipt_path(root, state["device_id"])
    atomic_write(target, json_bytes(receipt))
    return receipt


def read_receipt(root: Path, device_id: str) -> dict[str, Any] | None:
    target = receipt_path(root, device_id)
    if not target.exists():
        return None
    data = json.loads(target.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ReceiptError(f"未知的回执结构版本：{device_id}")
    if data.get("device_id") != device_id:
        raise ReceiptError(f"回执身份与文件名不符：{device_id}")
    return data


def read_all_receipts(root: Path) -> list[dict[str, Any]]:
    """Read every device receipt; a device that never reported is simply absent."""
    directory = root / RECEIPT_DIR
    if not directory.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        device_id = path.stem
        try:
            receipt = read_receipt(root, device_id)
        except (ReceiptError, ValueError, OSError):
            continue
        if receipt is not None:
            results.append(receipt)
    return results


def device_summary(receipts: list[Mapping[str, Any]], *, this_device: str | None = None, now: str | None = None) -> list[dict[str, Any]]:
    """Describe each device as reported-at, never as live or online.

    A device only ever shows the time it last reported.  It is never presented
    as currently online or in real-time sync.
    """
    stamp = now or datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for receipt in receipts:
        device = receipt.get("device_id")
        status = receipt.get("config_status")
        if status not in STATUS_CODES:
            status = "not_configured"
        rows.append({
            "device_id": device,
            "is_this_device": device == this_device,
            "status": status,
            "reported_at": receipt.get("reported_at"),
            "applied_version": receipt.get("applied_version"),
            "statement": f"最近报告于 {receipt.get('reported_at') or '未知时间'}",
            "live": False,
        })
    return rows


def _prepare_workspace(remote: str) -> Path:
    """A throwaway workspace that talks to the real remote, not to a local path."""
    workspace = Path(tempfile.mkdtemp(prefix="ai-config-receipts-"))
    _git(workspace, "init", "-q")
    _git(workspace, "remote", "add", "origin", remote)
    _git(workspace, "fetch", "origin", RECEIPT_BRANCH, check=False)
    # ``git rev-parse FETCH_HEAD`` echoes the argument even when it fails, so the
    # verified form is required to tell "branch exists" from "branch missing".
    if _git(workspace, "rev-parse", "--verify", "--quiet", "FETCH_HEAD", check=False):
        _git(workspace, "checkout", "-q", "-B", RECEIPT_BRANCH, "FETCH_HEAD")
    else:
        # An empty branch is a normal first-publish condition.
        _git(workspace, "checkout", "-q", "-B", RECEIPT_BRANCH)
    if not (workspace / ".git").exists():
        raise ReceiptError("回执工作区创建失败。")
    return workspace


def publish_receipt(root: Path, state: Mapping[str, Any], *, retries: int = 3) -> dict[str, Any]:
    """Publish one device receipt on the dedicated branch of the source remote.

    The user's checked-out branch is never switched: a temporary workspace
    commits on top of the receipt branch and pushes it to the URL the source
    checkout actually points at.  A lost race with another device retries; a
    genuine divergence is reported as pending rather than force pushed.
    """
    if not (root / ".git").exists():
        raise ReceiptUnavailable("配置源的 Git 仓库尚未初始化，回执未上报。")
    remote = remote_url(root)
    if not remote:
        raise ReceiptUnavailable("配置源没有远端地址，回执只保存在本机，未上报。")
    validate_state(state)
    receipt = shared_receipt(state)
    if not receipt_is_sensitive_free(receipt):
        raise ReceiptError("回执包含本机路径或敏感值，已拒绝上报。")
    workspace = _prepare_workspace(remote)
    try:
        target = receipt_path(workspace, state["device_id"])
        atomic_write(target, json_bytes(receipt))
        _git(workspace, "add", "--", f"{RECEIPT_DIR}/{state['device_id']}.json")
        _git(workspace, "config", "user.name", "ai-config", check=False)
        _git(workspace, "config", "user.email", "ai-config@localhost", check=False)
        _git(workspace, "commit", "-q", "-m", f"receipt: {state['device_id']}")
        for _ in range(max(1, retries)):
            push = subprocess.run(
                ["git", "-C", str(workspace), "push", "origin", f"HEAD:{RECEIPT_BRANCH}"],
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=_GIT_TIMEOUT,
                check=False,
                env=_GIT_ENV,
            )
            if push.returncode == 0:
                return {
                    "status": "uploaded",
                    "device_id": state["device_id"],
                    "branch": RECEIPT_BRANCH,
                    "receipt": receipt,
                }
            # Another device advanced the branch: rebase and retry, never force.
            _git(workspace, "fetch", "origin", RECEIPT_BRANCH, check=False)
            rebase = subprocess.run(
                ["git", "-C", str(workspace), "rebase", "FETCH_HEAD"],
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=_GIT_TIMEOUT,
                check=False,
                env=_GIT_ENV,
            )
            if rebase.returncode != 0:
                _git(workspace, "rebase", "--abort", check=False)
                raise ReceiptError("回执分支发生分叉，已保留本机状态，未强制推送。")
        raise ReceiptError("回执上报遇到并发推进，稍后重试即可，本机状态未受影响。")
    finally:
        import shutil
        shutil.rmtree(workspace, ignore_errors=True)


def fetch_receipts(root: Path) -> list[dict[str, Any]]:
    """Read receipts from the dedicated branch of the source remote.

    A source without a remote simply has no shared receipts yet; that is an
    empty result, not an error.
    """
    remote = remote_url(root)
    if not remote:
        return []
    workspace = Path(tempfile.mkdtemp(prefix="ai-config-receipts-read-"))
    try:
        _git(workspace, "init", "-q")
        _git(workspace, "remote", "add", "origin", remote)
        _git(workspace, "fetch", "origin", RECEIPT_BRANCH, check=False)
        if not _git(workspace, "rev-parse", "--verify", "--quiet", "FETCH_HEAD", check=False):
            return []
        _git(workspace, "checkout", "-q", "-f", "FETCH_HEAD", check=False)
        return read_all_receipts(workspace)
    except ReceiptError:
        return []
    finally:
        import shutil
        shutil.rmtree(workspace, ignore_errors=True)
