"""Deterministic comparison of hand-written rules against the store.

Users usually copy the same rules into every agent before adopting ai-config,
with small edits here and there.  ``scan`` and ``migrate`` compare those copies
line by line against the store: a line is *known* when its normalized key
already appears in a store topic.  Nothing is rewritten, summarized or merged
by a model -- normalization only removes differences that carry no meaning
(Unicode form, line endings, surrounding and repeated whitespace, Markdown list
and heading markers, a trailing full stop).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata
from typing import Iterable

from .config_status import managed_block

_SPACES = re.compile(r"[ \t　]+")
_MARKERS = re.compile(r"^(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+|\[[ xX]\]\s+)+")
_TRIVIAL = re.compile(r"^[\s#>*+\-_=|`~:.·]*$")
_TRAILING = re.compile(r"[。．.;；,，]+$")


def normalize(line: str) -> str:
    """The display form of a line: NFC, trimmed, single spaces."""
    return _SPACES.sub(" ", unicodedata.normalize("NFC", line).strip())


def key(line: str) -> str:
    """The comparison key: markers and a trailing full stop do not matter."""
    text = _MARKERS.sub("", normalize(line))
    return _TRAILING.sub("", text).strip().casefold()


def is_trivial(line: str) -> bool:
    text = normalize(line)
    return not text or bool(_TRIVIAL.fullmatch(text)) or text.startswith("<!--") and text.endswith("-->")


def split_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


@dataclass(frozen=True)
class Line:
    number: int
    text: str
    key: str


def meaningful_lines(text: str, *, start: int = 1) -> list[Line]:
    lines: list[Line] = []
    for offset, raw in enumerate(split_lines(text)):
        if is_trivial(raw):
            continue
        lines.append(Line(start + offset, normalize(raw), key(raw)))
    return lines


@dataclass(frozen=True)
class Outside:
    """Text of a rules file outside the ai-config managed block."""

    before: str
    after: str
    has_block: bool
    block_error: str | None
    after_start: int

    @property
    def text(self) -> str:
        return self.before + self.after

    def lines(self) -> list[Line]:
        return meaningful_lines(self.before) + meaningful_lines(self.after, start=self.after_start)


def outside_block(data: bytes) -> Outside:
    """Split a rules file around its managed block.

    A malformed block (duplicated or reversed markers) is reported, not
    guessed around: the whole file then counts as outside content.
    """
    text = data.decode("utf-8-sig")
    block, error = managed_block(data)
    if error is not None or block is None:
        return Outside(text, "", False, None if error in {"no_managed_block", "missing"} else error, 1)
    start = data.index(block)
    before = data[:start].decode("utf-8-sig")
    after = data[start + len(block):].decode("utf-8")
    after_start = len(split_lines(data[: start + len(block)].decode("utf-8-sig")))
    return Outside(before, after, True, None, after_start)


def store_keys(store_root: Path, topics: Iterable[str] | None = None) -> set[str]:
    """Comparison keys of every line already in the store's rule topics."""
    from .config import SHARED_RULE_TOPICS

    names = list(topics) if topics is not None else list(SHARED_RULE_TOPICS)
    keys: set[str] = set()
    for name in [*names, "imported"]:
        path = store_root / "common" / f"{name}.md"
        if path.is_file():
            keys.update(line.key for line in meaningful_lines(path.read_text(encoding="utf-8")))
    return keys


@dataclass(frozen=True)
class Comparison:
    total: int
    known: tuple[Line, ...]
    unique: tuple[Line, ...]

    @property
    def fully_known(self) -> bool:
        return self.total > 0 and not self.unique


def compare(lines: Iterable[Line], known_keys: set[str]) -> Comparison:
    items = list(lines)
    known = tuple(line for line in items if line.key in known_keys)
    unique = tuple(line for line in items if line.key not in known_keys)
    return Comparison(len(items), known, unique)
