"""Record installed dependency closure; scope build / runtime locks separately."""
from __future__ import annotations
import argparse
from importlib import metadata
from pathlib import Path
import re
from packaging.requirements import Requirement


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["server", "desktop"], required=True)
    args = parser.parse_args()
    roots = ["fastapi", "uvicorn", "sqlalchemy", "psycopg", "psycopg-binary", "pyjwt", "cryptography", "httpx"] if args.scope == "server" else ["tomlkit", "cryptography", "httpx", "keyring", "pyinstaller", "pyinstaller-hooks-contrib"]
    todo = [(name, set()) for name in roots]
    versions: dict[str, str] = {}
    while todo:
        name, extras = todo.pop()
        distribution = metadata.distribution(name)
        key = normalized(distribution.metadata["Name"])
        if key in versions:
            continue
        versions[key] = distribution.version
        for text in distribution.requires or []:
            requirement = Requirement(text)
            if requirement.marker is None or any(requirement.marker.evaluate({"extra": extra}) for extra in {"", *extras}):
                todo.append((requirement.name, requirement.extras))
    root = Path(__file__).resolve().parents[1]
    filename = "server/requirements.lock.txt" if args.scope == "server" else "desktop/requirements-windows.lock.txt"
    header = "# Resolved on Windows / Python 3.14; versions locked, platform wheels resolved at install.\n"
    (root / filename).write_text(header + "".join(f"{name}=={versions[name]}\n" for name in sorted(versions)), encoding="utf-8")


if __name__ == "__main__":
    main()
