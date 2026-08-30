"""Stage orchestration: pre-split, extract, validate, canonicalise.

`parse_manifest` is the package's one entry point. It never trusts an extractor's
`ordinal`, `source_line` or `id` — those are recomputed here, deterministically, from
`source_span` against `raw`. That is what makes the provenance invariant hold (every
`source_span` verbatim in `raw`, `ordinal == raw.index(source_span)`) regardless of what
the model returns, and it is why the only thing worth retrying is a `source_span` that
fails that check — a structural failure, not a scored one.
"""

from __future__ import annotations

from mff_contracts import Manifest, Requirement

from .errors import ManifestParseError, NonVerbatimSpanError
from .presplit import TextChunk, presplit
from .protocol import RequirementExtractor

__all__ = ["DEFAULT_MAX_ATTEMPTS", "parse_manifest"]

# "Cap the re-asks" (brief) without a specified number. Three matches the retry budget the
# editor service uses for slices (B8) — one clean attempt plus two chances to self-correct
# a non-verbatim span before this is treated as a hard failure rather than bad luck.
DEFAULT_MAX_ATTEMPTS = 3

_RETRY_NOTE = (
    "\n\n[The previous response included a source_span that was not an exact, verbatim "
    "substring of the text above: {span!r}. Every source_span must be copied "
    "character-for-character from the text above — do not paraphrase, translate, or "
    "correct its spelling.]"
)


def _verify_span(span: str, raw: str) -> None:
    if not span or span not in raw:
        raise NonVerbatimSpanError(span)


def _line_of(ordinal: int, raw: str) -> int:
    """1-indexed line number containing character offset `ordinal` in `raw`."""
    return raw.count("\n", 0, ordinal) + 1


async def _extract_chunk(
    chunk: TextChunk,
    extractor: RequirementExtractor,
    raw: str,
    max_attempts: int,
) -> list[Requirement]:
    """Call the extractor on one chunk, re-asking on a non-verbatim span.

    Returns the extractor's requirements unchanged on success — `_canonicalise` is what
    actually recomputes ordinal/source_line/id, this function only decides whether the
    result is trustworthy enough to keep.
    """
    text = chunk.text
    last_error: NonVerbatimSpanError | None = None
    for _attempt in range(max_attempts):
        items = await extractor.extract(text, offset=chunk.offset)
        try:
            for req in items:
                _verify_span(req.source_span, raw)
                if req.constraint is not None:
                    _verify_span(req.constraint.source_span, raw)
        except NonVerbatimSpanError as exc:
            last_error = exc
            text = chunk.text + _RETRY_NOTE.format(span=exc.span)
            continue
        return items

    raise ManifestParseError(
        f"extractor kept returning a non-verbatim source_span after {max_attempts} "
        f"attempts on the chunk at offset {chunk.offset}: {last_error}"
    ) from last_error


def _canonicalise(items: list[Requirement], raw: str) -> list[Requirement]:
    """Recompute ordinal/source_line from source_span, sort, then assign ids.

    Sorting by `(ordinal, text)` — never `ordinal` alone — is load-bearing: two
    requirements can share both a span and an ordinal (the fixture has two such pairs),
    and without the `text` tiebreak their relative order, and therefore which gets the
    lower id, would depend on whatever order the extractor happened to return them in.
    """
    resolved: list[Requirement] = []
    for req in items:
        _verify_span(req.source_span, raw)
        ordinal = raw.index(req.source_span)
        updates: dict[str, object] = {"ordinal": ordinal, "source_line": _line_of(ordinal, raw)}
        if req.constraint is not None:
            _verify_span(req.constraint.source_span, raw)
            constraint_ordinal = raw.index(req.constraint.source_span)
            updates["constraint"] = req.constraint.model_copy(
                update={"source_line": _line_of(constraint_ordinal, raw)}
            )
        resolved.append(req.model_copy(update=updates))

    resolved.sort(key=lambda r: (r.ordinal, r.text))
    return [
        r.model_copy(update={"id": f"R-{index:02d}"}) for index, r in enumerate(resolved, start=1)
    ]


async def parse_manifest(
    raw: str,
    *,
    extractor: RequirementExtractor,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Manifest:
    """Free text -> `Manifest`. Never invents a requirement; never silently drops one.

    Two stages: `presplit` (deterministic) hands the extractor one paragraph-shaped chunk
    at a time; `extractor.extract` (one small model call per chunk) does the one thing a
    splitter cannot — decide how many discrete, individually-checkable requirements a
    chunk names (a count is not a repetition; one line can name two things), and link a
    constraint back to the item it qualifies even when they are lines apart. Everything
    after that — ordinal, source_line, id — is recomputed deterministically from
    `source_span`, never trusted from the model.
    """
    collected: list[Requirement] = []
    for chunk in presplit(raw):
        collected.extend(await _extract_chunk(chunk, extractor, raw, max_attempts))
    return Manifest(raw=raw, requirements=_canonicalise(collected, raw))
