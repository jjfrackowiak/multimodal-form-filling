"""Stage 1 of manifest parsing: a deterministic pre-split.

Splits the raw manifest into paragraph-shaped chunks on blank lines — cheap, reproducible
and with no model output anywhere in its path — and records each chunk's character offset
into `raw`, so provenance can be recovered without trusting the model's own arithmetic
later.

Line boundaries deliberately stay *inside* a chunk rather than becoming split points. The
fixture's hardest case is a constraint on line 10 that qualifies an item on line 4, six
lines away; a splitter that hands the model one line at a time can never let it make that
link, and neither can a splitter that hands it one line-derived requirement at a time. A
blank line is the one boundary safe to split on: nothing in this domain (a manifest is one
continuous list of what a form must contain) puts a dependency across a paragraph break.
`fleet-vehicle-return/manifest.txt` has no blank lines, so it pre-splits to exactly one
chunk — the whole document goes to the model in the "one small model call" that stage 2
makes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["TextChunk", "presplit"]

# A run of two or more newlines (each optionally trailing horizontal whitespace) is one
# blank-line separator, however many blank lines it spans.
_BLANK_LINE = re.compile(r"(?:\n[ \t]*){2,}")


@dataclass(frozen=True)
class TextChunk:
    """A verbatim slice of the manifest, with the character offset it starts at.

    `raw[offset : offset + len(text)] == text` holds by construction — every chunk
    `presplit` produces is a genuine substring of what it split, at the position it
    claims.
    """

    text: str
    offset: int


def presplit(raw: str) -> list[TextChunk]:
    """Split `raw` into chunks on blank lines, preserving verbatim substrings and offsets.

    A chunk with only whitespace is dropped — it names nothing an extractor could turn
    into a requirement. If nothing survives that (an empty or whitespace-only manifest),
    the whole (possibly empty) text is returned as one chunk, so "no chunks" — which would
    silently skip the model call entirely — never happens.
    """
    chunks: list[TextChunk] = []
    pos = 0
    for match in _BLANK_LINE.finditer(raw):
        piece = raw[pos : match.start()]
        if piece.strip():
            chunks.append(TextChunk(text=piece, offset=pos))
        pos = match.end()
    tail = raw[pos:]
    if tail.strip():
        chunks.append(TextChunk(text=tail, offset=pos))
    if not chunks:
        chunks.append(TextChunk(text=raw, offset=0))
    return chunks
