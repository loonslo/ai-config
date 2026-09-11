"""Explicit, lock-coordinated Git transport for the private memory repository."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sync_core.config import absolute
from sync_core.snapshots import mark_all_heads_confirmed
from sync_core.transaction import SyncLock
from sync_core.transport import GitTransport
from sync_core.utils import SECRET
from sync_core.utils import atomic_write, json_bytes


class TransportCommandError(RuntimeError):
    """A transport failure that requires a later retry."""


class _SyncCompat:
    ROOT = ROOT
    SECRET = SECRET


sync = _SyncCompat()


def git(root: Path, *args: str) -> str:
    """Compatibility helper used by existing callers and tests."""
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, encoding="utf-8", errors="replace").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "pull", "push"])
    parser.add_argument("--local", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.local.read_text(encoding="utf-8-sig"))
    root = absolute(config["memory_repo"])
    if root == sync.ROOT or sync.ROOT in root.parents:
        raise ValueError("Memory repository must be outside ai-config")
    state = absolute(config["state_dir"]) if config.get("state_dir") else root.parent / f".{root.name}.sync-state"
    with SyncLock(state):
        transport = GitTransport(root)
        if args.action == "init":
            transport.init()
            print("Local memory repository ready. No remote was created.")
            return
        transport.validate()
        if args.action == "pull":
            commit = transport.pull_ff_only()
            print(f"Memory Git pull complete: {commit[:12] if commit else 'no commit'}")
            return
        try:
            result = transport.push_confirmed()
            # A second confirmed commit records which heads were included in
            # the remote read-back. It is deliberately not inferred before push.
            if mark_all_heads_confirmed(root):
                result = transport.push_confirmed()
        except RuntimeError as error:
            atomic_write(state / "transport.json", json_bytes({"schema_version": 1, "status": "pending", "detail": str(error)}))
            print("Memory Git push pending; local commit was preserved")
            raise TransportCommandError(str(error)) from error
        atomic_write(state / "transport.json", json_bytes({"schema_version": 1, "status": result.status, "commit": result.commit}))
        print(f"Memory Git push complete: {result.commit[:12] if result.commit else 'no commit'}; status={result.status}")


if __name__ == "__main__":
    try:
        main()
    except TransportCommandError as error:
        raise SystemExit(3) from error
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(3 if isinstance(error, RuntimeError) else 1)
