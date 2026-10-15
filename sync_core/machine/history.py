"""Bounded history scanning and independently validated ZIP64 history parts."""
from __future__ import annotations

from dataclasses import dataclass, field
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tomllib
from typing import Callable, Iterator, Any
import uuid
import zipfile

from .bundle import BundleError, _member_name, _object
from .privacy import secret_hits, redact
from .catalog import denied_path

FORMAT = 'ai-machine-history'
HEX = re.compile(r'^[0-9a-f]{64}$')


class HistoryError(BundleError):
    code = 'E7507'

    def __init__(self):
        super().__init__('历史备份不完整、已变化或与主备份不匹配；未恢复历史文件。请核对全部分包后重试。')


@dataclass(frozen=True)
class HistoryLimits:
    part_bytes: int = 8 * 1024**3
    total_bytes: int = 64 * 1024**3
    members: int = 20_000
    parts: int = 128
    line_bytes: int = 1024**2
    chunk_bytes: int = 1024**2
    manifest_bytes: int = 16 * 1024**2
    metadata_bytes: int = 64 * 1024**2
    scanned_nodes: int = 100_000
    flagged_lines: int = 20_000

    def __post_init__(self):
        if any(type(v) is not int or v < 1 for v in vars(self).values()):
            raise ValueError('invalid history limits')


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def history_path(agent: str, relative: str) -> bool:
    if not isinstance(relative, str) or not isinstance(agent, str):
        raise HistoryError()
    _member_name(relative)
    if denied_path(relative):
        return False
    parts = relative.split('/')
    if any(':' in p or p.endswith(('.', ' ')) or re.search(r'[<>"|?*]', p)
           or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p) for p in parts):
        return False
    if agent == 'claude':
        return relative == 'history.jsonl' or len(parts) == 3 and parts[0] == 'projects' and parts[-1].endswith('.jsonl')
    if agent == 'codex':
        return relative in {'history.jsonl', 'session_index.jsonl'} or len(parts) >= 2 and parts[0] in {'sessions', 'archived_sessions'}
    return False


def _no_links(path: Path) -> None:
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise HistoryError()


@dataclass
class HistorySource:
    agent: str
    relative: str
    path: Path
    raw_hash: str = ''
    mtime: int = 0
    size: int = 0
    redactions: int = 0
    hit_lines: list[int] = field(default_factory=list)
    hit_kinds: set[str] = field(default_factory=set)
    high_confidence: bool = False
    hit_line_count: int = 0
    line_sample_limit: int = 2000

    @property
    def id(self) -> str:
        return _hash([self.agent, self.relative])


class _Rejected(ValueError):
    pass


class _LineFramer:
    """Retain byte order and split encoded newlines only at code-unit boundaries."""
    def __init__(self, cap: int, *, jsonl: bool):
        self.pending = bytearray()
        self.cap = cap
        self.jsonl = jsonl
        self.encoding: str | None = None
        self.width = 1

    def _detect(self) -> None:
        head = bytes(self.pending[:4])
        for bom, encoding, width in ((b'\xff\xfe\x00\x00', 'utf-32-le', 4),
                                    (b'\x00\x00\xfe\xff', 'utf-32-be', 4),
                                    (b'\xff\xfe', 'utf-16-le', 2), (b'\xfe\xff', 'utf-16-be', 2)):
            if head.startswith(bom):
                self.encoding, self.width = encoding, width
                return
        if len(head) == 4:
            if head[1:] == b'\x00\x00\x00':
                self.encoding, self.width = 'utf-32-le', 4
            elif head[:3] == b'\x00\x00\x00':
                self.encoding, self.width = 'utf-32-be', 4
            elif head[1] == head[3] == 0:
                self.encoding, self.width = 'utf-16-le', 2
            elif head[0] == head[2] == 0:
                self.encoding, self.width = 'utf-16-be', 2
        self.encoding = self.encoding or 'utf-8'

    def feed(self, chunk: bytes, *, final: bool = False) -> Iterator[bytes]:
        self.pending.extend(chunk)
        if self.encoding is None:
            if len(self.pending) < 4 and not final:
                return
            self._detect()
        delimiter = '\n'.encode(self.encoding)
        start = 0
        while True:
            end = self.pending.find(delimiter, start)
            if end < 0:
                break
            if end % self.width:
                start = end + 1
                continue
            stop = end + len(delimiter)
            if stop > self.cap:
                raise _Rejected('line_too_long')
            value = bytes(self.pending[:stop]); del self.pending[:stop]
            start = 0
            yield value
        if len(self.pending) > self.cap:
            raise _Rejected('line_too_long')
        if final and self.pending:
            yield bytes(self.pending)
            self.pending.clear()


def _json_line(value: bytes, encoding: str) -> None:
    text = value.decode(encoding).lstrip('\ufeff')
    if text.strip():
        json.loads(text, object_pairs_hook=_object, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def _open_private_key(value: bytes) -> bool:
    for hit in secret_hits(value):
        if hit.kind == 'private_key':
            text = value[hit.start:hit.end].decode(hit.encoding, errors='replace')
            if not re.search(r'-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', text):
                return True
    return False


def _records(handle, framer: _LineFramer) -> Iterator[tuple[bytes, int]]:
    """Buffer raw PEM blocks together so their body never survives header redaction."""
    block = bytearray(); line_number = 1; block_line = 1; key_open = False
    ends = [marker.encode(encoding) for encoding in ('utf-8','utf-16-le','utf-16-be','utf-32-le','utf-32-be')
            for marker in ('-----END PRIVATE KEY-----','-----END RSA PRIVATE KEY-----',
                           '-----END EC PRIVATE KEY-----','-----END OPENSSH PRIVATE KEY-----')]
    def consume(line: bytes) -> Iterator[tuple[bytes, int]]:
        nonlocal line_number, block_line, key_open
        if not block:
            block_line = line_number
        block.extend(line)
        line_number += 1
        if len(block) > framer.cap:
            raise _Rejected('private_key_block_too_long')
        if key_open and not any(marker in line for marker in ends):
            return
        key_open = not framer.jsonl and _open_private_key(bytes(block))
        if not key_open:
            yield bytes(block), block_line
            block.clear()
    while chunk := handle.read(64 * 1024):
        for line in framer.feed(chunk):
            yield from consume(line)
    for line in framer.feed(b'', final=True):
        yield from consume(line)
    if block:
        yield bytes(block), block_line


def _lines(source: HistorySource, limits: HistoryLimits, policy: str, *, snapshot: bool = False) -> Iterator[bytes]:
    _no_links(source.path)
    before = source.path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise _Rejected('not_regular_file')
    if snapshot:
        source.hit_lines.clear(); source.hit_kinds.clear()
        source.high_confidence = False; source.hit_line_count = 0
    raw = hashlib.sha256(); count = 0; line_number = 0
    structured = Path(source.relative).suffix.lower() in {'.json', '.toml'}
    format_buffer = bytearray(); format_overflow = False
    with source.path.open('rb') as handle:
        framer = _LineFramer(limits.line_bytes, jsonl=source.relative.endswith('.jsonl'))
        for line, line_number in _records(handle, framer):
            raw.update(line)
            if len(line) > limits.line_bytes:
                raise _Rejected('line_too_long')
            try:
                if framer.jsonl:
                    _json_line(line, framer.encoding)
            except (ValueError, UnicodeError, RecursionError):
                raise _Rejected('invalid_jsonl') from None
            hits = secret_hits(line)
            count += len(hits)
            if hits:
                if snapshot:
                    locations = sorted({line_number + hit.line - 1 for hit in hits})
                    source.hit_line_count += len(locations)
                    source.hit_lines.extend(locations[:max(0, source.line_sample_limit - len(source.hit_lines))])
                    source.hit_kinds.update(h.kind for h in hits)
                    source.high_confidence |= any(h.confidence == 'high' for h in hits)
                if policy == 'skip':
                    raise _Rejected('secret_file_skipped')
                line, _ = redact(line, hits)
                try:
                    if framer.jsonl:
                        _json_line(line, framer.encoding)
                except (ValueError, UnicodeError, RecursionError):
                    raise _Rejected('redaction_parse_failed') from None
                if secret_hits(line):
                    raise _Rejected('redaction_incomplete')
            if structured and not format_overflow:
                if len(format_buffer) + len(line) <= limits.line_bytes:
                    format_buffer.extend(line)
                else:
                    format_buffer.clear(); format_overflow = True
            yield line
        if structured and count:
            if format_overflow:
                raise _Rejected('redaction_format_limit')
            try:
                if source.relative.lower().endswith('.json'):
                    _json_line(bytes(format_buffer), framer.encoding)
                else:
                    tomllib.loads(format_buffer.decode('utf-8-sig'))
            except (ValueError, UnicodeError, RecursionError):
                raise _Rejected('redaction_parse_failed') from None
    after = source.path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise HistoryError()
    fingerprint = (raw.hexdigest(), after.st_mtime_ns, after.st_size, count)
    if snapshot:
        source.raw_hash, source.mtime, source.size, source.redactions = fingerprint
    elif fingerprint != (source.raw_hash, source.mtime, source.size, source.redactions):
        raise HistoryError()


def _chunks(source: HistorySource, limits: HistoryLimits, policy: str) -> Iterator[bytes]:
    cap = min(limits.chunk_bytes, limits.part_bytes)
    buf = bytearray()
    for line in _lines(source, limits, policy):
        for start in range(0, len(line), cap):
            piece = line[start:start + cap]
            if len(buf) + len(piece) > cap:
                yield bytes(buf); buf.clear()
            buf.extend(piece)
            if len(buf) == cap:
                yield bytes(buf); buf.clear()
    if buf:
        yield bytes(buf)


@dataclass
class HistoryPlan:
    sources: list[HistorySource]
    entries: list[list[dict[str, Any]]]
    exclusions: list[dict[str, str]]
    limits: HistoryLimits
    policy: str
    flagged: list[dict[str, Any]] = field(default_factory=list)
    sampled_lines: int = 0

    @property
    def set_id(self) -> str:
        return _hash(self.entries)

    def report(self) -> dict[str, Any]:
        return {'set_id': self.set_id, 'parts': len(self.entries), 'files': len(self.sources),
                'bytes': sum(e['size'] for part in self.entries for e in part),
                'redactions': sum(s.redactions for s in self.sources), 'exclusions': self.exclusions}

    def verify_sources_unchanged(self) -> bool:
        try:
            for source in self.sources:
                for _ in _lines(source, self.limits, self.policy):
                    pass
            return True
        except (OSError, ValueError):
            return False

    def references(self, destination: Path) -> list[dict[str, str]]:
        return [{'name': f'{destination.stem}-历史-{index}.zip', 'content_id': _hash(entries)}
                for index, entries in enumerate(self.entries, 1)]

    def record_hits(self, source: HistorySource, *, skipped: bool) -> None:
        if source.hit_line_count:
            self.sampled_lines += len(source.hit_lines)
            self.flagged.append({'id': f'h{len(self.flagged)+1:04d}', 'rule_id': 'CC-18' if source.agent == 'claude' else 'CX-14',
                                 'logical_path': f'{source.agent}:history/{source.relative}', 'lines': source.hit_lines,
                                 'kinds': sorted(source.hit_kinds), 'confidence': 'high' if source.high_confidence else 'heuristic',
                                 'action': 'skipped' if skipped else 'redacted', 'redactions': 0 if skipped else source.redactions,
                                 'line_count': source.hit_line_count, 'lines_truncated': source.hit_line_count > len(source.hit_lines)})


def publish_files(sources: list[Path], destinations: list[Path], *, verify: Callable[[], None] = lambda: None) -> None:
    """Create a set without replacing existing paths; roll back only owned files."""
    if len(sources) != len(destinations) or len(set(destinations)) != len(destinations):
        raise HistoryError()
    published: dict[Path, tuple[int, int]] = {}
    try:
        for path in destinations:
            _no_links(path)
            if not path.is_absolute() or not path.parent.is_dir() or path.exists():
                raise HistoryError()
        for source, target in zip(sources, destinations):
            _no_links(source); _no_links(target)
            try:
                os.link(source, target)
                st = target.stat(); published[target] = (st.st_dev, st.st_ino)
            except OSError as error:
                if error.errno not in {errno.EPERM, errno.EACCES, errno.EXDEV, errno.EINVAL, errno.ENOTSUP}:
                    raise
                with target.open('xb') as output:
                    st = os.fstat(output.fileno()); published[target] = (st.st_dev, st.st_ino)
                    with source.open('rb') as input:
                        while chunk := input.read(1024**2):
                            output.write(chunk)
                    output.flush(); os.fsync(output.fileno())
        verify()
    except BaseException:
        for path, identity in published.items():
            if path.exists() and not path.is_symlink() and not path.is_junction():
                st = path.stat()
                if (st.st_dev, st.st_ino) == identity:
                    path.unlink()
        raise


def prepare_history(roots: dict[str, Path], *, selected: bool, policy: str = 'redact',
                    limits: HistoryLimits = HistoryLimits(), excluded: Callable[[Path, Path], bool] = lambda p, r: False) -> HistoryPlan:
    if policy not in {'redact', 'skip'}:
        raise ValueError('invalid history privacy policy')
    sources = []; exclusions = []; entries: list[list[dict[str, Any]]] = []
    plan = HistoryPlan(sources, entries, exclusions, limits, policy)
    if not selected:
        return plan
    seen = 0; total_bytes = 0; part_bytes = 0; metadata_bytes = 0
    for agent, root in sorted(roots.items()):
        if agent not in {'claude', 'codex'}:
            continue
        candidates: list[Path] = []
        for name in ('history.jsonl', 'session_index.jsonl') if agent == 'codex' else ('history.jsonl',):
            path = root / name
            if path.is_file():
                candidates.append(path)
        for folder in ('projects',) if agent == 'claude' else ('sessions', 'archived_sessions'):
            base = root / folder
            if not base.is_dir() or excluded(base, root):
                continue
            try:
                _no_links(base)
            except HistoryError:
                exclusions.append({'agent': agent, 'relative': folder, 'reason': 'link_blocked'}); continue
            for directory, names, files in os.walk(base, followlinks=False):
                names.sort(); files.sort(); seen += len(names) + len(files)
                if seen > limits.scanned_nodes:
                    raise HistoryError()
                directory_path = Path(directory)
                kept=[]
                for name in names:
                    child=directory_path/name
                    relative=child.relative_to(root).as_posix()
                    reason='protected_history_path' if denied_path(relative) else 'link_blocked' if child.is_symlink() or child.is_junction() else 'excluded_by_config' if excluded(child,root) else ''
                    if reason:
                        exclusions.append({'agent':agent,'relative':relative,'reason':reason})
                    else:
                        kept.append(name)
                names[:]=kept
                if agent == 'claude' and len(directory_path.relative_to(root).parts) >= 2:
                    names.clear()
                candidates.extend(directory_path / name for name in files if agent == 'codex' or name.endswith('.jsonl'))
        for path in sorted(set(candidates)):
            relative = path.relative_to(root).as_posix()
            if excluded(path, root):
                continue
            if denied_path(relative):
                exclusions.append({'agent':agent,'relative':relative,'reason':'protected_history_path'});continue
            try:
                _no_links(path)
            except HistoryError:
                exclusions.append({'agent': agent, 'relative': relative, 'reason': 'link_blocked'}); continue
            source = HistorySource(agent, relative, path)
            source.line_sample_limit = min(2000, max(0, limits.flagged_lines - plan.sampled_lines))
            try:
                if not history_path(agent, relative):
                    exclusions.append({'agent':agent,'relative':relative,'reason':'unsafe_history_path'});continue
                for _ in _lines(source, limits, policy, snapshot=True):
                    pass
                # Build only metadata; the second pass verifies the first snapshot.
                staged: list[dict[str, Any]] = []; offset = 0; staged_metadata = 0
                for chunk in _chunks(source, limits, policy):
                    if len(staged) >= limits.parts * limits.members or offset + len(chunk) + total_bytes > limits.total_bytes:
                        raise HistoryError()
                    staged.append({'source_id': source.id, 'agent': agent, 'relative': relative,
                                   'offset': offset, 'size': len(chunk), 'sha256': hashlib.sha256(chunk).hexdigest(),
                                   'archive_path': f'files/{source.id}/{offset:020d}.bin'})
                    staged_metadata += len(_json(staged[-1]))
                    if metadata_bytes + staged_metadata + limits.parts*1024 > limits.metadata_bytes:
                        raise HistoryError()
                    offset += len(chunk)
                if not staged:  # Empty JSONL still has a restorable identity.
                    staged.append({'source_id': source.id, 'agent': agent, 'relative': relative, 'offset': 0,
                                   'size': 0, 'sha256': hashlib.sha256(b'').hexdigest(), 'archive_path': f'files/{source.id}/{0:020d}.bin'})
                    staged_metadata = len(_json(staged[-1]))
            except _Rejected as error:
                plan.record_hits(source, skipped=True)
                exclusions.append({'agent': agent, 'relative': relative, 'reason': str(error)}); continue
            except OSError:
                plan.record_hits(source, skipped=True)
                exclusions.append({'agent': agent, 'relative': relative, 'reason': 'unreadable'}); continue
            plan.record_hits(source, skipped=False)
            metadata_bytes += staged_metadata
            if metadata_bytes + limits.parts*1024 > limits.metadata_bytes:
                raise HistoryError()
            sources.append(source)
            for entry in staged:
                if not entries or len(entries[-1]) >= limits.members or part_bytes + entry['size'] > limits.part_bytes:
                    entries.append([]); part_bytes = 0
                entries[-1].append(entry)
                part_bytes += entry['size']; total_bytes += entry['size']
                if len(entries) > limits.parts or total_bytes > limits.total_bytes:
                    raise HistoryError()
    return plan


def write_history(plan: HistoryPlan, destinations: list[Path], *, parent_content_id: str) -> list[dict[str, Any]]:
    """Stage all parts, validate their set, then publish without replacing files."""
    if len(destinations) != len(plan.entries) or not HEX.fullmatch(parent_content_id) or len(set(destinations)) != len(destinations):
        raise HistoryError()
    if any(not p.is_absolute() or not p.parent.is_dir() for p in destinations):
        raise HistoryError()
    owned: list[Path] = []
    staged = [p.with_name(p.name + '.' + uuid.uuid4().hex + '.partial') for p in destinations]
    streams = {s.id: iter(_chunks(s, plan.limits, plan.policy)) for s in plan.sources}
    try:
        for path in destinations:
            _no_links(path)
            if path.exists():
                raise HistoryError()
        for index, (path, entries) in enumerate(zip(staged, plan.entries), 1):
            with path.open('xb') as handle:
                owned.append(path)
                with zipfile.ZipFile(handle, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                    for entry in entries:
                        chunk = next(streams[entry['source_id']], b'')
                        if len(chunk) != entry['size'] or hashlib.sha256(chunk).hexdigest() != entry['sha256']:
                            raise HistoryError()
                        with archive.open(entry['archive_path'], 'w', force_zip64=True) as member:
                            member.write(chunk)
                    manifest = {'format': FORMAT, 'schema_version': 1, 'parent_content_id': parent_content_id,
                                'set_id': plan.set_id, 'part_index': index, 'part_count': len(plan.entries),
                                'entries': entries, 'content_id': _hash(entries)}
                    data = _json(manifest)
                    if len(data) > plan.limits.manifest_bytes:
                        raise HistoryError()
                    archive.writestr('manifest.json', data)
        for stream in streams.values():
            if next(stream, None) is not None:
                raise HistoryError()
        validate_history(staged, parent_content_id=parent_content_id, limits=plan.limits)
        publish_files(staged, destinations)
        return [{'name': p.name, 'content_id': _hash(entries)} for p, entries in zip(destinations, plan.entries)]
    finally:
        for stream in streams.values():
            stream.close()
        for path in owned:
            path.unlink(missing_ok=True)


class _JsonlGate:
    """Check encoded records even when archive segments cut code units."""
    def __init__(self, cap: int, *, jsonl: bool = True):
        self.framer = _LineFramer(cap, jsonl=jsonl)
        self.cap = cap

    def line(self, value: bytes) -> None:
        if len(value) > self.cap or secret_hits(value):
            raise HistoryError()
        if self.framer.jsonl:
            _json_line(value, self.framer.encoding)

    def feed(self, chunk: bytes) -> None:
        for value in self.framer.feed(chunk):
            self.line(value)

    def finish(self) -> None:
        for value in self.framer.feed(b'', final=True):
            self.line(value)


def validate_history(paths: list[Path], *, parent_content_id: str, limits: HistoryLimits = HistoryLimits(),
                     source_summary: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Read and hash one segment at a time; return metadata, never payloads."""
    parts = []; total = 0; positions: dict[str, int] = {}; members = set(); metadata_bytes=0
    current_sid = None; gate = _JsonlGate(limits.line_bytes)
    summaries=[]; source_hash=hashlib.sha256(); source_record=None
    if len(paths) > limits.parts or not HEX.fullmatch(parent_content_id):
        raise HistoryError()
    try:
        for index, path in enumerate(paths, 1):
            _no_links(path)
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist(); names = [i.filename for i in infos]
                if len(names) != len(set(names)) or len(infos) > limits.members + 1:
                    raise HistoryError()
                if any(i.flag_bits & 1 or i.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                       or i.external_attr >> 16 & 0o170000 == 0o120000 for i in infos):
                    raise HistoryError()
                mi = archive.getinfo('manifest.json')
                metadata_bytes+=mi.file_size
                if metadata_bytes>limits.metadata_bytes:
                    raise HistoryError()
                if mi.file_size > limits.manifest_bytes or mi.file_size > max(1, mi.compress_size) * 1000:
                    raise HistoryError()
                with archive.open(mi) as member:
                    metadata = member.read(limits.manifest_bytes + 1)
                if len(metadata) > limits.manifest_bytes:
                    raise HistoryError()
                manifest = json.loads(metadata, object_pairs_hook=_object)
                if set(manifest) != {'format','schema_version','parent_content_id','set_id','part_index','part_count','entries','content_id'} or manifest['format'] != FORMAT or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
                    raise HistoryError()
                if manifest['parent_content_id'] != parent_content_id or type(manifest['part_index']) is not int or manifest['part_index'] != index or type(manifest['part_count']) is not int or manifest['part_count'] != len(paths):
                    raise HistoryError()
                entries = manifest['entries']
                if not isinstance(entries, list) or not entries or len(entries) > limits.members or manifest['content_id'] != _hash(entries):
                    raise HistoryError()
                if set(names) != {'manifest.json', *(e['archive_path'] for e in entries)}:
                    raise HistoryError()
                part_bytes = 0
                for e in entries:
                    if set(e) != {'source_id','agent','relative','offset','size','sha256','archive_path'} or not history_path(e['agent'], e['relative']):
                        raise HistoryError()
                    sid = _hash([e['agent'], e['relative']])
                    if e['source_id'] != sid or type(e['offset']) is not int or e['offset'] != positions.get(sid, 0) or type(e['size']) is not int or not 0 <= e['size'] <= min(limits.chunk_bytes, limits.part_bytes) or not isinstance(e['sha256'], str) or not HEX.fullmatch(e['sha256']):
                        raise HistoryError()
                    if e['archive_path'] != f"files/{sid}/{e['offset']:020d}.bin":
                        raise HistoryError()
                    if e['archive_path'] in members:
                        raise HistoryError()
                    members.add(e['archive_path'])
                    if current_sid != sid:
                        gate.finish()
                        if source_record is not None:
                            summaries.append({**source_record,'sha256':source_hash.hexdigest(),'size':positions[current_sid]})
                        if sid in positions:
                            raise HistoryError()
                        current_sid = sid
                        gate = _JsonlGate(limits.line_bytes, jsonl=e['relative'].endswith('.jsonl'))
                        source_hash=hashlib.sha256(); source_record={'source_id':sid,'agent':e['agent'],'relative':e['relative']}
                    info = archive.getinfo(e['archive_path'])
                    if info.file_size != e['size'] or info.external_attr >> 16 & 0o170000 == 0o120000:
                        raise HistoryError()
                    if info.file_size > max(1, info.compress_size) * 1000:
                        raise HistoryError()
                    digest = hashlib.sha256(); size = 0
                    with archive.open(info) as member:
                        while chunk := member.read(min(limits.chunk_bytes, 1024**2)):
                            size += len(chunk); digest.update(chunk)
                            if size > e['size']:
                                raise HistoryError()
                            gate.feed(chunk)
                            source_hash.update(chunk)
                    if size != e['size'] or digest.hexdigest() != e['sha256']:
                        raise HistoryError()
                    positions[sid] = e['offset'] + e['size']; part_bytes += size
                total += part_bytes
                if part_bytes > limits.part_bytes or total > limits.total_bytes:
                    raise HistoryError()
                parts.append(manifest)
        gate.finish()
        if source_record is not None:
            summaries.append({**source_record,'sha256':source_hash.hexdigest(),'size':positions[current_sid]})
        if parts and any(p['set_id'] != _hash([p['entries'] for p in parts]) for p in parts):
            raise HistoryError()
        if source_summary is not None:
            source_summary.extend(summaries)
        return parts
    except (OSError, ValueError, KeyError, TypeError, RecursionError, zipfile.BadZipFile, EOFError):
        raise HistoryError() from None
