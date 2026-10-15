"""Value-free credential detection and offset-preserving redaction."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Literal, Sequence

SecretKind = Literal["token", "private_key", "bearer", "jwt", "url_userinfo", "kv_secret", "env_assign"]
Confidence = Literal["high", "heuristic"]
EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
URL_USERINFO = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/]+@", re.I)
_ESCAPE = re.compile(r"\\+u([0-9a-fA-F]{4})|\\([nrt])")
_SECRET_NAME = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|PASSWD|AUTH", re.I)
_PLACEHOLDER = "<REDACTED>"
_VALUE = r'''(?P<value>"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;{}\[\]"']+)'''
_PATTERNS = (
    ("token", "high", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}")),
    ("private_key", "high", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?(?:-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|$)", re.S)),
    ("bearer", "high", re.compile(r"""(?i:Authorization)\s*["']?\s*:\s*["']?\s*(?i:Bearer)\s+(?P<value>[A-Za-z0-9._~+/-]{12,})""")),
    ("jwt", "high", re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("url_userinfo", "high", re.compile(r"""\b[a-z][a-z0-9+.-]*://(?P<value>[^\s/"']+)@""", re.I)),
    ("kv_secret", "heuristic", re.compile(r'''(?<![A-Za-z0-9_])(?i:api[_ -]?key|access[_ -]?token|[A-Z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD|PASSWD|AUTH)|密码|口令|密钥|令牌)["']?\s*[:=：]\s*''' + _VALUE)),
    ("env_assign", "heuristic", re.compile(r'''(?im:^[ \t]*(?:export[ \t]+)?[A-Z0-9_]*(?:PASSWORD|PASSWD|TOKEN|API_KEY|SECRET|AUTH)["']?\s*=\s*)''' + _VALUE)),
)

@dataclass(frozen=True)
class SecretHit:
    kind: SecretKind
    confidence: Confidence
    line: int
    start: int = field(repr=False)
    end: int = field(repr=False)
    encoding: str = field(default='text',repr=False)
    priority: int = field(default=0,repr=False)

def secret_name(name: str) -> bool:
    return bool(_SECRET_NAME.search(name))

def _decoded(text: str) -> tuple[str, list[tuple[int, int, int, int]]]:
    chunks, spans = [], []
    position = decoded_length = 0
    for match in _ESCAPE.finditer(text):
        chunk = text[position:match.start()]
        chunks.append(chunk)
        decoded_length += len(chunk)
        chunks.append(chr(int(match[1], 16)) if match[1] else {"n": "\n", "r": "\r", "t": "\t"}[match[2]])
        spans.append((decoded_length, decoded_length + 1, match.start(), match.end()))
        decoded_length += 1
        position = match.end()
    if not spans:
        return text, []
    chunks.append(text[position:])
    return "".join(chunks), spans

def _original_offset(position: int, spans: list[tuple[int, int, int, int]], *, end: bool = False) -> int:
    offset = 0
    for decoded_start, decoded_end, original_start, original_end in spans:
        if position < decoded_start:
            break
        if position < decoded_end:
            return original_end if end else original_start
        offset = original_end - decoded_end
    return position + offset

def personal_text(value: str | bytes) -> bool:
    """Output hygiene only: an email must not block backup or restore."""
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    decoded, _ = _decoded(text)
    return bool(EMAIL.search(decoded) or URL_USERINFO.search(decoded))

def _text_hits(text: str) -> list[SecretHit]:
    decoded, spans = _decoded(text)
    hits = []
    for kind, confidence, pattern in _PATTERNS:
        for match in pattern.finditer(decoded):
            start, end = match.span("value") if "value" in match.groupdict() else match.span()
            value = decoded[start:end]
            if value.startswith(('"', "'")) and value.endswith(value[0]):
                start, end = start + 1, end - 1
                value = decoded[start:end]
            if not value or value == _PLACEHOLDER:
                continue
            original_start = _original_offset(start, spans)
            original_end = _original_offset(end - 1, spans, end=True)
            if not any(a <= end - 1 < b for a, b, _, _ in spans):
                original_end += 1
            hits.append(SecretHit(kind, confidence, text.count("\n", 0, original_start) + 1, original_start, original_end))
    return hits


def _offsets(text: str, encoding: str, positions: set[int]) -> dict[int,int]:
    if encoding=='latin-1' or encoding=='utf-8' and text.isascii():
        return {p:p for p in positions}
    if encoding.startswith('utf-32'):
        return {p:p*4 for p in positions}
    result={};previous=0;count=0
    for position in sorted(positions):
        count+=len(text[previous:position].encode(encoding,errors='surrogatepass'))
        result[position]=count;previous=position
    return result


def _candidates(data: bytes):
    try:
        text=data.decode('utf-8');primary='utf-8'
    except UnicodeDecodeError:
        text=data.decode('latin-1');primary='latin-1'
    yield text,primary,0,0
    if primary=='utf-8' and b'\x00' not in data:
        return
    rank=1
    for width in (2,4):
        if width==4 and b'\x00\x00' not in data:
            continue
        for offset in range(width):
            stop=len(data)-(len(data)-offset)%width
            if stop<=offset:
                continue
            for encoding in (f'utf-{width*8}-le',f'utf-{width*8}-be'):
                # UTF-16 surrogatepass roundtrips arbitrary code units. UTF-32
                # replaces invalid units, with exactly one character per unit.
                text=data[offset:stop].decode(encoding,errors='surrogatepass' if width==2 else 'replace')
                yield text,encoding,offset,rank
                rank+=1


def secret_hits(data: bytes | str) -> list[SecretHit]:
    if isinstance(data,str):
        hits=_text_hits(data)
    else:
        hits=[]
        for text,encoding,offset,rank in _candidates(data):
            found=_text_hits(text)
            if not found:
                continue
            positions=_offsets(text,encoding,{p for h in found for p in (h.start,h.end)})
            hits.extend(SecretHit(h.kind,h.confidence,h.line,offset+positions[h.start],offset+positions[h.end],encoding,rank) for h in found)
    # High confidence wins; aligned views win over an overlapping shifted view.
    picked = []
    for hit in sorted(hits, key=lambda h: (h.confidence != "high", h.kind != "env_assign", h.priority, h.start, -(h.end - h.start))):
        if not any(hit.start < old.end and old.start < hit.end for old in picked):
            picked.append(hit)
    return sorted(picked, key=lambda h: h.start)

def redact(data: bytes, hits: Sequence[SecretHit], *, only: Confidence | None = None) -> tuple[bytes, int]:
    selected = [hit for hit in hits if only is None or hit.confidence == only]
    text_hits=[h for h in selected if h.encoding=='text']
    offsets=_offsets(data.decode('utf-8'),'utf-8',{p for h in text_hits for p in (h.start,h.end)}) if text_hits else {}
    for hit in sorted(selected, key=lambda hit: hit.start, reverse=True):
        start,end=(offsets[hit.start],offsets[hit.end]) if hit.encoding=='text' else (hit.start,hit.end)
        encoding='utf-8' if hit.encoding=='text' else hit.encoding
        data=data[:start]+_PLACEHOLDER.encode(encoding)+data[end:]
    return data, len(selected)

def private_text(value: str | bytes) -> bool:
    return bool(secret_hits(value))

def private_metadata(value: Any) -> bool:
    return private_text(json.dumps(value, ensure_ascii=False, allow_nan=False))


def public_value(value: Any) -> Any:
    """Display-only copy: preserve synced bodies, hide contacts/credentials in outputs."""
    if isinstance(value,str):
        decoded,_=_decoded(value)
        if private_text(decoded):
            return '<敏感内容已隐藏>'
        if EMAIL.search(decoded) and not EMAIL.search(value):
            return '<邮箱已隐藏>'
        return EMAIL.sub('<邮箱已隐藏>',value)
    if isinstance(value,dict):
        return {public_value(k):public_value(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):
        return [public_value(v) for v in value]
    return value
