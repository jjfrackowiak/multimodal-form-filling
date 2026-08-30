"""`parse_docx` against the real fixture: reqs 14/15, and the DoD's round-trip claim."""

from __future__ import annotations

import hashlib
import io

from docx import Document

from mff_docmodel import parse_docx

# From the fixture: 17 inline photographs (2 pairs are byte-identical duplicates once
# extracted from the .docx — see the docstring on test_image_sha256_matches_extraction),
# 9 numbered "Heading 1" sections, and a 5-row x 2-col vehicle table.
EXPECTED_IMAGE_NODES = 17
EXPECTED_HEADINGS = 9
EXPECTED_TABLE_CELLS = 5 * 2


def test_parse_smoke(derivative_docx_bytes: bytes) -> None:
    nodes = parse_docx(derivative_docx_bytes)
    assert nodes  # not empty


def test_node_ids_are_stable_across_two_parses(derivative_docx_bytes: bytes) -> None:
    """The DoD's headline claim: same bytes in, same ids out, every time."""
    first = parse_docx(derivative_docx_bytes)
    second = parse_docx(derivative_docx_bytes)
    assert [n.id for n in first] == [n.id for n in second]
    assert [n.model_dump() for n in first] == [n.model_dump() for n in second]


def test_node_ids_are_unique(derivative_docx_bytes: bytes) -> None:
    nodes = parse_docx(derivative_docx_bytes)
    ids = [n.id for n in nodes]
    assert len(ids) == len(set(ids))


def test_heading_count(derivative_docx_bytes: bytes) -> None:
    nodes = parse_docx(derivative_docx_bytes)
    headings = [n for n in nodes if n.kind == "heading"]
    assert len(headings) == EXPECTED_HEADINGS
    assert headings[0].text == "1. Pod maską"
    assert headings[-1].text == "9. Uwagi"


def test_image_node_count(derivative_docx_bytes: bytes) -> None:
    nodes = parse_docx(derivative_docx_bytes)
    images = [n for n in nodes if n.kind == "image"]
    assert len(images) == EXPECTED_IMAGE_NODES
    assert all(n.image_sha256 for n in images)


def test_table_cells_get_ids(derivative_docx_bytes: bytes) -> None:
    """DoD 7: the fixture's vehicle table has five rows."""
    nodes = parse_docx(derivative_docx_bytes)
    cells = [n for n in nodes if n.kind == "table_cell"]
    assert len(cells) == EXPECTED_TABLE_CELLS
    ids = {c.id for c in cells}
    assert ids == {f"t0.r{r}.c{c}" for r in range(5) for c in range(2)}
    by_id = {c.id: c.text for c in cells}
    assert by_id["t0.r0.c0"] == "Marka i model"
    assert by_id["t0.r0.c1"] == "Nissan Qashqai"


def test_captions_follow_their_photograph(derivative_docx_bytes: bytes) -> None:
    """Section '5. Przednia szyba' is the R-05/R-06 shape: two photo+caption pairs."""
    nodes = parse_docx(derivative_docx_bytes)
    captions = [n.text for n in nodes if n.kind == "caption"]
    assert "Komora silnika" in captions
    assert "Szyba przednia od środka" in captions
    assert "Szyba przednia z zewnątrz" in captions


def test_paragraph_and_image_children_reference_the_enclosing_heading(
    derivative_docx_bytes: bytes,
) -> None:
    nodes = parse_docx(derivative_docx_bytes)
    by_id = {n.id: n for n in nodes}
    heading = next(n for n in nodes if n.text == "5. Przednia szyba")
    children = [n for n in nodes if n.parent_id == heading.id]
    assert len(children) >= 4  # two images, two captions
    assert all(by_id[c.parent_id].id == heading.id for c in children if c.parent_id)


def test_image_sha256_matches_extraction(derivative_docx_bytes: bytes) -> None:
    """The hash on the node is exactly the sha256 of the bytes as embedded — recomputing
    it independently (via the raw image parts) must agree, node by node."""
    document = Document(io.BytesIO(derivative_docx_bytes))
    expected_hashes = {
        hashlib.sha256(part.blob).hexdigest() for part in document.part.package.image_parts
    }
    nodes = parse_docx(derivative_docx_bytes)
    image_hashes = {n.image_sha256 for n in nodes if n.kind == "image"}
    assert image_hashes <= expected_hashes
    # 17 embedded pictures, 15 distinct sha256 — two pairs are duplicate files.
    assert len(expected_hashes) == 15
