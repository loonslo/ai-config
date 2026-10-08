"""Conservative, injectable process detection without external dependencies."""
from __future__ import annotations

import csv
import os
from pathlib import Path
import subprocess
from typing import Callable, Iterable


def process_names(*, run: Callable = subprocess.run, os_name: str = os.name) -> list[str]:
    if os_name == "nt":
        command = ["tasklist", "/FO", "CSV", "/NH"]
    else:
        command = ["ps", "-A", "-o", "comm="]
    result = run(command, capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
    if result.returncode:
        raise ValueError("process inventory unavailable")
    return ([row[0] for row in csv.reader(result.stdout.splitlines()) if row]
            if os_name == "nt" else [Path(line.strip()).name for line in result.stdout.splitlines() if line.strip()])


def running_apps(configured: Iterable[str], *, processes: Iterable[str] | None = None) -> list[str]:
    observed = process_names() if processes is None else processes
    names = {Path(name.replace('\\', '/')).name.casefold() for name in observed}
    return sorted({name for name in configured if name.casefold() in names})
