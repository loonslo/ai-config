"""Reliable, file-level synchronization primitives for ai-config."""

from .merge import MergeConflict, MergeResult, merge, three_way_merge, validate_file_map
from .snapshots import SnapshotError, create_snapshot, load_snapshot, mark_all_heads_confirmed, mark_head_confirmed, restore_snapshot
from .transaction import PlannedChanges, SyncBusyError, recover_transactions, transaction

__all__ = [
    "MergeConflict",
    "MergeResult",
    "PlannedChanges",
    "SnapshotError",
    "SyncBusyError",
    "create_snapshot",
    "load_snapshot",
    "mark_all_heads_confirmed",
    "mark_head_confirmed",
    "merge",
    "recover_transactions",
    "restore_snapshot",
    "three_way_merge",
    "transaction",
    "validate_file_map",
]
