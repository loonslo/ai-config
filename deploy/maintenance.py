"""Offline maintenance. Backups require a stopped API and a new target directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def compose(*args: str, **kwargs):
    root = Path(__file__).resolve().parent
    return subprocess.run(["docker", "compose", "-f", str(root / "compose.yaml"), *args], check=True, **kwargs)


def stopped() -> None:
    response = compose("ps", "--status", "running", "-q", "api", stdout=subprocess.PIPE)
    if response.stdout.strip():
        raise ValueError("Stop the API explicitly before backup / restore.")


def storage_path() -> Path:
    root = Path(os.environ["AI_SYNC_STORAGE_HOST"]).absolute()
    if not root.is_absolute() or any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError("Storage path must be explicit and contain no links")
    return root


def hashes(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Backup cannot contain links")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def backup(destination: Path) -> None:
    stopped()
    storage = storage_path()
    if destination.exists() or not destination.parent.is_dir() or destination.is_relative_to(storage):
        raise ValueError("Choose a new backup directory outside storage")
    before = hashes(storage)
    stage = Path(tempfile.mkdtemp(dir=destination.parent, prefix="ai-sync-backup-"))
    try:
        with (stage / "database.dump").open("xb") as output:
            compose("exec", "-T", "db", "pg_dump", "-U", "ai_sync", "-d", "ai_sync", "-Fc", stdout=output)
        shutil.copytree(storage, stage / "packages")
        after = hashes(storage)
        if before != after or before != hashes(stage / "packages"):
            raise ValueError("Package storage changed during backup")
        record = {"schema": 1, "created": int(time.time()), "files": hashes(stage)}
        (stage / "backup.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.rename(stage, destination)
    except Exception:
        # This stage was created within the explicit destination parent.
        shutil.rmtree(stage)
        raise


def restore(source: Path, *, confirmed: bool) -> None:
    stopped()
    storage = storage_path()
    record = json.loads((source / "backup.json").read_text(encoding="utf-8"))
    actual = hashes(source)
    actual.pop("backup.json", None)
    if record.get("schema") != 1 or record.get("files") != actual:
        raise ValueError("Backup hashes do not match")
    if storage.exists() and any(storage.iterdir()):
        raise ValueError("Restore requires an empty package destination; no overwrite")
    query = compose("exec", "-T", "db", "psql", "-U", "ai_sync", "-d", "ai_sync", "-Atc",
                    "select count(*) from information_schema.tables where table_schema='public'", stdout=subprocess.PIPE)
    if query.stdout.strip() != b"0":
        raise ValueError("Restore requires an empty PostgreSQL database")
    print(f"Restore plan: backup={source}; package destination={storage}; database=compose db/ai_sync")
    if not confirmed:
        print("Preview only. Use --confirm on these exact empty targets.")
        return
    storage.mkdir(parents=True, exist_ok=True)
    for child in (source / "packages").iterdir():
        target = storage / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)
    with (source / "database.dump").open("rb") as stream:
        compose("exec", "-T", "db", "pg_restore", "-U", "ai_sync", "-d", "ai_sync", "--single-transaction", "--exit-on-error", stdin=stream)
    if hashes(storage) != hashes(source / "packages"):
        raise ValueError("Restored package verification failed; keep API stopped")
    print("Restore bytes verified; start API and perform list/download/decrypt/import validation separately.")


def cleanup(*, confirm: bool = False, age_days: int = 7) -> None:
    """Delete only expired incomplete sessions; committed history is immutable."""
    stopped()
    from sqlalchemy import create_engine, select, delete
    from sqlalchemy.orm import Session
    from server.models import Upload, Part
    storage = storage_path()
    engine = create_engine(os.environ["AI_SYNC_DATABASE_URL"])
    with Session(engine) as session, session.begin():
        rows = session.scalars(select(Upload).where(Upload.version.is_(None), Upload.created < time.time() - age_days * 86400)).all()
        for row in rows:
            target = storage / "staging" / row.owner / row.id
            if not target.resolve().is_relative_to((storage / "staging").resolve()):
                raise ValueError("Cleanup escaped staging")
            print(f"Expired upload {row.id}: {row.size} reserved bytes")
            if confirm:
                if target.exists():
                    shutil.rmtree(target)
                session.execute(delete(Part).where(Part.upload == row.id))
                session.delete(row)
    print("Confirmed cleanup" if confirm else "Preview only; committed versions are not removed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "restore", "cleanup"])
    parser.add_argument("--path", type=Path)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if args.action == "cleanup":
        cleanup(confirm=args.confirm)
    elif args.path is None or not args.path.is_absolute():
        parser.error("--path must be an explicit absolute path")
    elif args.action == "backup":
        backup(args.path)
    else:
        restore(args.path, confirmed=args.confirm)


if __name__ == "__main__":
    main()
