"""Compile — `DerivativeArtifact` / `NetNewArtifact` → `.docx` bytes + `RenderMap`.

Comments are **not** attached here — `attach_comments` is a separate call over the bytes
either function returns. Splitting the two means the byte-identical-body promise for
derivative is a property of `compile_derivative` alone, provable with zero `ReviewComment`s
in play: it returns `source` untouched and a map of where things are, nothing more.

Net-new is "the easy one" (per the brief) precisely because there is no existing structure
to preserve — the compiler is free to build the document *and* the map in the same pass,
recording each entry's span the moment it writes it.
"""

from __future__ import annotations

from docx import Document
from mff_contracts import DerivativeArtifact, NetNewArtifact, RenderMap, RunSpan

from ._io import dump_document
from .parse import walk

__all__ = ["compile_derivative", "compile_netnew"]


def compile_derivative(artifact: DerivativeArtifact, source: bytes) -> tuple[bytes, RenderMap]:
    """Build the `RenderMap` for a client's document without touching it.

    The returned bytes are `source`, unchanged — a derivative compile never mutates the
    client's document; only `attach_comments` does, and only by adding comment markup.
    Re-walking `source` (rather than trusting `artifact.nodes` blindly) is what guarantees
    the ids in the returned map agree with what `parse_docx` would produce from these exact
    bytes right now, not whatever `artifact.nodes` said when it was last persisted.
    """
    # `artifact.nodes`/`artifact.comments` are not needed to build the map — see docstring.
    _, _, spans = walk(source)
    return source, RenderMap(anchor_to_span=spans)


def compile_netnew(artifact: NetNewArtifact) -> tuple[bytes, RenderMap]:
    """Render a `FormDraft` from nothing, recording each entry's span as it is written.

    A `Section` has no `Anchor.kind` of its own (only `"node"`, `"entry"` and `"document"`
    exist), so section headings are written for structure but never enter the map — a
    review comment can only ever target one of its entries.
    """
    document = Document()
    spans: dict[str, RunSpan] = {}

    document.add_heading(artifact.form_id, level=0)

    for section in artifact.draft.sections:
        document.add_heading(section.title, level=1)
        for entry in section.entries:
            paragraph = document.add_paragraph()
            paragraph.add_run(entry.value or "")
            for image in entry.images:
                # No bytes to embed: compiling here has no network access and receives
                # only a content-addressed `BlobRef`, never the blob itself. Recording the
                # reference in text keeps it visible instead of silently dropping it.
                paragraph.add_run(f"  [zdjęcie: {image.sha256[:12]}]")
            paragraph_index = len(document.paragraphs) - 1
            spans[entry.id] = RunSpan(
                paragraph_index=paragraph_index,
                run_start=0,
                run_end=len(paragraph.runs) - 1,
            )

    return dump_document(document), RenderMap(anchor_to_span=spans)
