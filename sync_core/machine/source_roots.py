"""Resolve declared sources from an injected home/environment, never global state."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .coverage import no_links


def desktop_root(home: Path, environ: Mapping[str, str]) -> Path | None:
    direct = Path(environ.get('APPDATA', str(home/'AppData/Roaming'))) / 'Claude'
    local = Path(environ.get('LOCALAPPDATA', str(home/'AppData/Local'))) / 'Packages'
    candidates = [direct]
    if local.is_dir() and no_links(local):
        candidates.extend(p/'LocalCache/Roaming/Claude' for p in sorted(local.glob('Claude_*')))
    existing = [p for p in candidates if p.is_dir() and no_links(p)]
    return next((p for p in existing if (p/'local-agent-mode-sessions').is_dir()), existing[0] if existing else None)
