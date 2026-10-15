"""Validate referenced siblings before planning bounded new-file restoration."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator
import zipfile

from sync_core.streaming import StreamContent, file_digest, no_links
from sync_core.utils import canonical_path
from .bundle import _member_name, _object
from .history import HistoryError, HistoryLimits, HEX, validate_history, _hash


def history_report(files: dict[str,bytes]) -> dict[str,Any] | None:
    if 'reports/history.json' not in files:
        return None
    try:
        report=json.loads(files['reports/history.json'],object_pairs_hook=_object)
        if not isinstance(report,dict) or set(report) != {'set_id','parts','files','bytes','redactions','exclusions','agents','packages'}:
            raise HistoryError()
        if not isinstance(report['set_id'],str) or not HEX.fullmatch(report['set_id']):
            raise HistoryError()
        for key in ('parts','files','bytes','redactions'):
            if type(report[key]) is not int or report[key]<0:
                raise HistoryError()
        if not isinstance(report['agents'],list) or any(a not in {'claude','codex'} for a in report['agents']) or len(report['agents'])!=len(set(report['agents'])):
            raise HistoryError()
        if not isinstance(report['exclusions'],list) or any(not isinstance(e,dict) or set(e)!={'agent','relative','reason'} or not all(isinstance(v,str) for v in e.values()) for e in report['exclusions']):
            raise HistoryError()
        refs=report['packages']
        if not isinstance(refs,list) or len(refs)!=report['parts'] or len(refs)>HistoryLimits().parts:
            raise HistoryError()
        if not refs and (report['set_id']!=_hash([]) or report['bytes'] or report['files'] or report['agents']):
            raise HistoryError()
        names=set();prefix=None
        for index,ref in enumerate(refs,1):
            if not isinstance(ref,dict) or set(ref)!={'name','content_id'} or not all(isinstance(v,str) for v in ref.values()):
                raise HistoryError()
            name=ref['name'];_member_name(name)
            if '/' in name or ':' in name or not name.endswith('.zip') or canonical_path(name) in names or not HEX.fullmatch(ref['content_id']):
                raise HistoryError()
            suffix=f'-历史-{index}.zip'
            if not name.endswith(suffix) or not name[:-len(suffix)]:
                raise HistoryError()
            base=name[:-len(suffix)]
            if prefix is not None and base!=prefix:
                raise HistoryError()
            prefix=base
            names.add(canonical_path(name))
        return report
    except (ValueError,TypeError,KeyError,RecursionError):
        raise HistoryError() from None


@dataclass
class HistorySet:
    report: dict[str,Any]
    paths: list[Path]
    parts: list[dict[str,Any]]
    sources: list[dict[str,Any]]
    fingerprints: dict[Path,str]
    segments: dict[str,list[tuple[Path,list[dict[str,Any]]]]] = field(default_factory=dict)

    def verify_unchanged(self) -> bool:
        try:
            return all(file_digest(p)==sha for p,sha in self.fingerprints.items())
        except (OSError,ValueError):
            return False

    def content(self, source: dict[str,Any]) -> StreamContent:
        def chunks() -> Iterator[bytes]:
            for path,entries in self.segments[source['source_id']]:
                no_links(path)
                with zipfile.ZipFile(path) as archive:
                    for entry in entries:
                        digest=hashlib.sha256();size=0
                        with archive.open(entry['archive_path']) as handle:
                            while chunk:=handle.read(1024**2):
                                size+=len(chunk);digest.update(chunk)
                                if size>entry['size']:
                                    raise HistoryError()
                                yield chunk
                        if size!=entry['size'] or digest.hexdigest()!=entry['sha256']:
                            raise HistoryError()
        return StreamContent(chunks,source['sha256'],source['size'])


def load_history(bundle: Path, manifest: dict[str,Any], files: dict[str,bytes], *, selected: bool) -> HistorySet | None:
    report=history_report(files)
    if report is None or not selected:
        return None
    paths=[bundle.parent/r['name'] for r in report['packages']]
    summaries=[]
    try:
        # Capture ZIP digests before validation and compare afterwards, too.
        fingerprints={p:file_digest(p) for p in paths}
        if any(v is None for v in fingerprints.values()):
            raise HistoryError()
        parts=validate_history(paths,parent_content_id=manifest['content_id'],source_summary=summaries)
        if len(summaries)!=report['files'] or sum(s['size'] for s in summaries)!=report['bytes'] or sorted({s['agent'] for s in summaries})!=sorted(report['agents']):
            raise HistoryError()
        if any(p['set_id']!=report['set_id'] or p['content_id']!=ref['content_id'] for p,ref in zip(parts,report['packages'])):
            raise HistoryError()
        result=HistorySet(report,paths,parts,summaries,fingerprints)
        for path,part in zip(paths,parts):
            groups={}
            for entry in part['entries']:
                groups.setdefault(entry['source_id'],[]).append(entry)
            for sid,entries in groups.items():
                result.segments.setdefault(sid,[]).append((path,entries))
        if not result.verify_unchanged():
            raise HistoryError()
        return result
    except (OSError,ValueError,KeyError,zipfile.BadZipFile):
        raise HistoryError() from None
