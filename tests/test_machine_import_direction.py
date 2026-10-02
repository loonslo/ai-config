"""The new offline implementation must stay independent of frozen modules."""
from __future__ import annotations

import ast
from pathlib import Path
import sys


FROZEN = ("sync_core.package", "sync_core.cloud", "sync_core.application")


def forbidden_imports(source: str) -> list[str]:
    failures: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [f"{module}.{alias.name}" for alias in node.names] if module == "sync_core" else [module]
            if node.level:
                continue
        else:
            continue
        for name in names:
            if any(name == frozen or name.startswith(frozen + ".") for frozen in FROZEN):
                failures.append(name)
            root = name.split(".")[0]
            if root not in sys.stdlib_module_names and root not in {"sync_core", "tomlkit", "__future__"}:
                failures.append(name)
    return failures


def test_machine_has_no_frozen_or_third_party_imports():
    root = Path(__file__).resolve().parents[1] / "sync_core" / "machine"
    for path in root.rglob("*.py"):
        assert forbidden_imports(path.read_text(encoding="utf-8")) == [], path


def test_guard_rejects_an_introduced_frozen_import():
    assert forbidden_imports("from sync_core.package import check\n")
    assert forbidden_imports("import requests\n")
