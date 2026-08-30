"""`attach_comments` — the bridge from ids to runs, and the only place that writes Word
comments.

`python-docx`'s `Document.add_comment(runs=...)` needs real `Run` objects; a `RenderMap`
gives us ids to `RunSpan`s. Resolving one to the other is all this module does. Two
`ReviewComment`s that share an anchor (the fixture's R-05/R-06 and R-08/R-09) simply call
`add_comment` twice against the same pair of runs — `python-docx` nests the resulting
`commentRangeStart`/`commentRangeEnd` pairs correctly on its own.

**`Run.add_comment` does not exist** — verified against the installed `python-docx==1.2.0`
source (`docx/text/run.py` has no such method; only `docx/document.py`'s
`Document.add_comment(runs=...)` is real). It appears only as a proposal in the project's
own design notes and was never shipped. Every call here goes through `Document.add_comment`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mff_contracts import RenderMap, ReviewComment

from ._io import dump_document, load_document

if TYPE_CHECKING:
    from docx.document import Document as DocxDocument
    from docx.text.run import Run

__all__ = ["attach_comments"]

_VERDICT_LABELS = {
    "pass": "PASS",
    "fail": "FAIL",
    "realised": "REALISED",
    "shortfall": "SHORTFALL",
    "not_applicable": "NOT_APPLICABLE",
    "unverified": "UNVERIFIED",
}

_RunPair = tuple["Run", "Run"]


def attach_comments(
    data: bytes,
    comments: list[ReviewComment],
    render_map: RenderMap,
    *,
    author: str,
) -> tuple[bytes, int, list[str]]:
    """Write every comment into `data`, resolving anchors through `render_map`.

    A comment's target — `anchor.kind == "document"`, or a `"node"`/`"entry"` id that is
    not (or no longer) in `render_map` — falls back to the last run in the document rather
    than being dropped: req 17's `unverified` verdict has no target *by construction* (the
    agent may never have identified one), and it still has to land somewhere a human
    reviewer will see it. Every id that took the fallback path is returned in the third
    element so a caller can watch it: if requirements land there routinely, region scoping
    upstream is not working.

    Returns `(document_bytes, comments_attached, unanchored_requirement_ids)`.
    """
    document = load_document(data)
    fallback = _fallback_run_pair(document)

    attached = 0
    unanchored: list[str] = []

    for comment in comments:
        run_pair = _resolve(comment, render_map, document)
        used_fallback = run_pair is None
        if run_pair is None:
            run_pair = fallback
        if run_pair is None:
            # No run anywhere in the document to anchor to (an empty document). Nothing
            # to attach a comment range to at all — this cannot happen for either compiler
            # in this package, both of which always emit at least one run, but it must not
            # be reported as "fell back" when nothing actually landed anywhere.
            continue

        first_run, last_run = run_pair
        document.add_comment(
            runs=[first_run, last_run],
            text=_render_text(comment),
            author=author,
            initials=_initials(author),
        )
        attached += 1
        if used_fallback:
            unanchored.append(comment.requirement_id)

    return dump_document(document), attached, unanchored


def _resolve(
    comment: ReviewComment, render_map: RenderMap, document: DocxDocument
) -> _RunPair | None:
    if comment.anchor.kind == "document":
        return None
    target_id = comment.anchor.target_id
    if target_id is None:  # unreachable given Anchor's own validator; kept for mypy
        return None
    span = render_map.anchor_to_span.get(target_id)
    if span is None:
        return None
    paragraphs = document.paragraphs
    if span.paragraph_index >= len(paragraphs):
        return None
    runs = paragraphs[span.paragraph_index].runs
    if span.run_start >= len(runs) or span.run_end >= len(runs):
        return None
    return runs[span.run_start], runs[span.run_end]


def _fallback_run_pair(document: DocxDocument) -> _RunPair | None:
    """The last paragraph in the document that has at least one run.

    Search from the end: a summary/signature paragraph is the natural place for a
    document-level finding to surface, and searching backwards means a trailing blank
    spacer paragraph (real in most templates) does not defeat the search.
    """
    for paragraph in reversed(document.paragraphs):
        if paragraph.runs:
            return paragraph.runs[0], paragraph.runs[-1]
    return None


def _render_text(comment: ReviewComment) -> str:
    label = _VERDICT_LABELS.get(comment.verdict, comment.verdict.upper())
    lines = [f"[{comment.requirement_id}] {label}", "", f"Uzasadnienie: {comment.justification}"]
    if comment.suggestion:
        lines += ["", f"Sugestia: {comment.suggestion}"]
    return "\n".join(lines)


def _initials(author: str) -> str:
    words = author.split()
    return "".join(word[0] for word in words[:2]).upper()
