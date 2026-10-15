"""The sole source-link exception, restricted to two in-home skill directories."""
from __future__ import annotations

import os
from pathlib import Path

from .bundle import BundleError
from .coverage import is_link, no_links


def link_target(home: Path, root: Path) -> tuple[Path, bool]:
    link = root/'skills'
    if not no_links(root):
        raise BundleError('E7501: unsafe skills root')
    if not is_link(link):
        return link, False
    raw = os.readlink(link)
    if raw.startswith('\\\\?\\'):
        raw = raw[4:]
    target = Path(raw)
    if not target.is_absolute():
        target = link.parent/target
    # Check the lexical destination BEFORE resolve can hide another link.
    if not no_links(target) or not target.is_dir():
        raise BundleError('E7501: linked skills destination')
    resolved = target.resolve()
    allowed = {home/'.cc-switch/skills',home/'.agents/skills'}
    if resolved not in {path.resolve() for path in allowed} or not resolved.is_relative_to(home.resolve()):
        raise BundleError('E7501: skills destination outside allowlist')
    count = 0
    for folder, dirs, files in os.walk(resolved,followlinks=False):
        dirs[:] = [name for name in dirs if name.casefold() != '.git']
        files = [name for name in files if name.casefold() not in {'.git', '.gitconfig', '.git-credentials', '.gitignore', '.gitattributes', '.gitmodules'}]
        count += len(dirs)+len(files)
        if count>100_000:
            raise BundleError('E7501: skills link scan exceeds limit')
        if any(is_link(Path(folder)/name) for name in (*dirs,*files)):
            raise BundleError('E7501: link inside skills destination')
    return resolved, True
