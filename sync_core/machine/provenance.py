"""Evidence-based skill origins; URLs and evidence never contain credentials."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re

from .collect_reinstall import _safe_url
from .coverage import no_links


@dataclass(frozen=True)
class ProvenanceHints:
    account: dict[str, str] = field(default_factory=dict)
    vendor_system: bool = False
    lock: dict | None = None
    siblings: dict[str, str] = field(default_factory=dict)


def _source(kind: str, evidence: str, confidence: str = 'exact', url=None, ref=None) -> dict:
    return {'kind':kind,'url':_safe_url(url),'ref':None,'evidence':evidence,'confidence':confidence}


def resolve_skill(skill: Path, *, hints: ProvenanceHints) -> dict:
    name = skill.name
    creator = hints.account.get(name)
    source, origin, derived, changes = None, 'unknown', None, 'unknown'
    if creator in {'user','anthropic'}:
        origin = 'user' if creator == 'user' else 'vendor_builtin'
        source = _source('account','manifest.creatorType')
    elif hints.vendor_system:
        origin, source = 'vendor_builtin', _source('account','codex.system')
    elif hints.lock is not None:
        entry = hints.lock.get(name)
        if isinstance(entry,dict):
            origin = 'third_party'
            source = _source('lockfile','skill-lock',url=entry.get('sourceUrl') or entry.get('source'))
        else:
            origin = 'user'
    # Git metadata is deliberately not queried; use only non-Git provenance evidence.
    if source is None and origin == 'unknown':
        package = skill/'package.json'
        if package.is_file() and no_links(package) and package.stat().st_size <= 1_000_000:
            try:
                raw = json.loads(package.read_bytes())
                repo = raw.get('repository') if isinstance(raw,dict) else None
                url = _safe_url(repo.get('url') if isinstance(repo,dict) else repo)
                if url:
                    origin, source = 'third_party', _source('package_json','package.json','derived',url=url)
            except (OSError,ValueError):
                pass
        if source is None and any((skill/name).is_file() and no_links(skill/name) for name in ('LICENSE','LICENSE.md','LICENSE.txt','COPYING')):
            origin, source = 'third_party', _source('license_only','license','guess')
        if source is None and name in hints.siblings:
            origin, derived = 'third_party', hints.siblings[name]
            source = _source('template','tmpl-sibling','derived')
    if source is None:
        source = _source('unknown','none','guess')
    return {'origin':origin,'source':source,'derived_from':derived,'local_changes':changes}
