"""Create a traceable artifact manifest without claiming installation validation."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notices", type=Path, help="Exact companion LICENSE/NOTICE archive")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    artifact = args.artifact.resolve(strict=True)
    if not artifact.is_file() or args.output.exists():
        raise SystemExit("Artifact must be a regular file; manifest must be new")
    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=root, text=True).strip()
    # Include tracked/untracked source bytes without reading user/runtime dirs.
    paths = set(git("ls-files").splitlines()) | set(git("ls-files", "--others", "--exclude-standard").splitlines())
    source = {}
    allowed = {"sync_core", "server", "desktop", "scripts", "schemas", "templates", "common", "deploy"}
    for name in sorted(paths):
        path = root / name
        if name.split("/")[0] in allowed and path.is_file() and not path.is_symlink():
            source[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"schema": 1, "source_commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
                "source_files": source, "source_digest": hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest(),
                "artifact": artifact.name, "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "size": artifact.stat().st_size,
                "native_install_verified": False, "signing": "not verified", "licenses": "docs/third-party-licenses.md"}
    if args.notices:
        notices = args.notices.resolve(strict=True)
        if not notices.is_file() or notices.is_symlink():
            raise SystemExit("Notices must be a regular archive")
        manifest["notice_archive"] = {"name": notices.name, "sha256": hashlib.sha256(notices.read_bytes()).hexdigest(), "size": notices.stat().st_size}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    print(args.output)


if __name__ == "__main__":
    main()
