"""DoD 3 — the assertion that makes derivative's promise real.

"A derivative compile must leave the body byte-identical to the input, with only comments
added." Tested two ways:

1. End to end (`compile_derivative` + `attach_comments`, several comments including the
   R-05/R-06 two-on-one-span shape): strip the comment ranges back out and the body must
   match the original, byte for byte.
2. Mutation testing the checker itself (CONTEXT.md's rule): break the body in three
   different ways and prove the same comparison catches every one. A byte-identical check
   that cannot fail is not a guarantee.
"""

from __future__ import annotations

from mff_contracts import Anchor, BlobRef, DerivativeArtifact, ReviewComment

from mff_docmodel import attach_comments, compile_derivative, parse_docx

from _xml import canonical, read_document_xml, strip_comment_ranges

AUTHOR = "AI Editor"


def _artifact(source: bytes) -> DerivativeArtifact:
    nodes = parse_docx(source)
    blob = BlobRef(
        uri="mem://s", content_type="application/vnd.docx", size_bytes=len(source), sha256="x"
    )
    return DerivativeArtifact(form_id="form_supplied", source=blob, nodes=nodes)


def _full_pipeline_output(source: bytes) -> bytes:
    artifact = _artifact(source)
    compiled_bytes, render_map = compile_derivative(artifact, source)
    headings = [n for n in artifact.nodes if n.kind == "heading"]

    comments = [
        ReviewComment(
            requirement_id="R-05",
            anchor=Anchor(kind="node", target_id=headings[4].id),  # "5. Przednia szyba"
            verdict="pass",
            justification="Windscreen photographed from the cabin, dashboard visible.",
        ),
        ReviewComment(
            requirement_id="R-06",
            anchor=Anchor(kind="node", target_id=headings[4].id),  # same span as R-05
            verdict="pass",
            justification="Windscreen photographed from outside, occupant visible.",
        ),
        ReviewComment(
            requirement_id="R-01",
            anchor=Anchor(kind="node", target_id=headings[0].id),
            verdict="fail",
            justification="Only one of two required engine-bay photographs was supplied.",
            suggestion="Supply a second photograph of the engine bay from another angle.",
        ),
        ReviewComment(
            requirement_id="R-99",
            anchor=Anchor(kind="document"),
            verdict="unverified",
            justification="No identifiable target for this requirement in the submitted form.",
        ),
    ]
    out_bytes, count, unanchored = attach_comments(compiled_bytes, comments, render_map, author=AUTHOR)
    assert count == 4
    assert unanchored == ["R-99"]
    return out_bytes


def test_byte_identical_body_end_to_end(derivative_docx_bytes: bytes) -> None:
    out_bytes = _full_pipeline_output(derivative_docx_bytes)

    before = canonical(read_document_xml(derivative_docx_bytes))
    after = strip_comment_ranges(read_document_xml(out_bytes))
    assert before == after


# --- Mutation testing the checker itself (CONTEXT.md: "break your own golden output in at
# --- least three ways and show each caught") -------------------------------------------


def _bodies(derivative_docx_bytes: bytes) -> tuple[bytes, bytes]:
    out_bytes = _full_pipeline_output(derivative_docx_bytes)
    before = canonical(read_document_xml(derivative_docx_bytes))
    after = strip_comment_ranges(read_document_xml(out_bytes))
    return before, after


def test_mutation_changed_visible_text_is_caught(derivative_docx_bytes: bytes) -> None:
    before, after = _bodies(derivative_docx_bytes)
    assert before == after  # baseline: real output passes

    mutated = after.replace(b"Komora silnika", b"Komora silnika ZMIENIONA")
    assert mutated != before


def test_mutation_removed_paragraph_text_is_caught(derivative_docx_bytes: bytes) -> None:
    before, after = _bodies(derivative_docx_bytes)
    assert before == after

    mutated = after.replace("<w:t>Bagażnik</w:t>".encode(), b"<w:t></w:t>", 1)
    assert mutated != before


def test_mutation_swapped_captions_is_caught(derivative_docx_bytes: bytes) -> None:
    """Simulates reordered/relabelled content: two distinctive captions traded places."""
    before, after = _bodies(derivative_docx_bytes)
    assert before == after

    placeholder = b"__SWAP__"
    mutated = after.replace("Fotel kierowcy".encode(), placeholder)
    mutated = mutated.replace("Fotel pasażera".encode(), "Fotel kierowcy".encode())
    mutated = mutated.replace(placeholder, "Fotel pasażera".encode())
    assert mutated != before
