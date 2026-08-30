"""Derivative parsing — `Node` extraction and the walk `compile_derivative` reuses.

Ids are positional (`p12`, `t0.r2.c1`) and **not minted** — acceptable here and only here,
because a derivative document never changes shape between one parse and the next: nothing
inserts, so nothing shifts (see the module docstring in `mff_contracts.docmodel`). Parsing
the same bytes twice walks the same paragraphs and tables in the same order and produces
the same ids.

`compile_derivative` calls `walk()` directly rather than re-implementing this traversal, so
a `Node.id` a caller saw from `parse_docx` is *guaranteed* — not just expected — to resolve
to the same `RunSpan` when the document is later compiled for comments.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from mff_contracts import Node, RunSpan

from ._images import EmbeddedImage, embedded_images_in_run
from ._io import load_document

__all__ = ["Walk", "parse_docx", "walk"]

_P_TAG = qn("w:p")
_TBL_TAG = qn("w:tbl")

_NodeKind = Literal["heading", "paragraph", "table_cell", "image", "caption"]


class Walk(NamedTuple):
    """The result of one traversal: nodes in document order, plus where each landed."""

    document: DocxDocument
    nodes: list[Node]
    spans: dict[str, RunSpan]


def parse_docx(data: bytes) -> list[Node]:
    """Every node in a client's `.docx`, in document order."""
    return walk(data).nodes


def walk(data: bytes) -> Walk:
    document = load_document(data)
    nodes: list[Node] = []
    spans: dict[str, RunSpan] = {}
    current_heading_id: str | None = None
    previous_kind: _NodeKind | None = None
    paragraph_index = 0
    table_index = 0

    for child in document.element.body:
        if child.tag == _P_TAG:
            paragraph = Paragraph(child, document)
            entries = _nodes_for_paragraph(
                paragraph, paragraph_index, current_heading_id, previous_kind, document
            )
            for node, span in entries:
                nodes.append(node)
                if span is not None:
                    spans[node.id] = span
            if entries:
                last_kind = entries[-1][0].kind
                previous_kind = last_kind
                if last_kind == "heading":
                    current_heading_id = entries[-1][0].id
            else:
                previous_kind = None
            paragraph_index += 1
        elif child.tag == _TBL_TAG:
            table = Table(child, document)
            nodes.extend(_table_cell_nodes(table, table_index))
            table_index += 1
            previous_kind = None

    return Walk(document=document, nodes=nodes, spans=spans)


def _nodes_for_paragraph(
    paragraph: Paragraph,
    index: int,
    heading_id: str | None,
    previous_kind: _NodeKind | None,
    document: DocxDocument,
) -> list[tuple[Node, RunSpan | None]]:
    image_runs = _image_bearing_runs(paragraph, document)
    if image_runs:
        return _image_nodes(index, heading_id, image_runs)

    text = paragraph.text.strip()
    if not text:
        # A structural spacer (blank paragraph between sections): real in the XML, but
        # nothing worth naming — round-tripping the body untouched does not require every
        # paragraph to own a Node.
        return []

    style_name = (paragraph.style.name or "") if paragraph.style is not None else ""
    kind: _NodeKind
    if style_name.startswith("Heading"):
        kind = "heading"
    elif previous_kind == "image":
        kind = "caption"
    else:
        kind = "paragraph"

    node = Node(
        id=f"p{index}",
        kind=kind,
        text=text,
        parent_id=None if kind == "heading" else heading_id,
    )
    span = RunSpan(paragraph_index=index, run_start=0, run_end=len(paragraph.runs) - 1)
    return [(node, span)]


def _image_bearing_runs(
    paragraph: Paragraph, document: DocxDocument
) -> list[tuple[int, EmbeddedImage]]:
    """`(run_index, first embedded image)` for every run in the paragraph that carries at
    least one decodable image. A run with more than one `<a:blip>` contributes only its
    first image — not a shape this fixture exercises, and not one this model needs to
    represent faithfully to stay correct about the ones it does."""
    found: list[tuple[int, EmbeddedImage]] = []
    for i, run in enumerate(paragraph.runs):
        images = embedded_images_in_run(run.element, document)
        if images:
            found.append((i, images[0]))
    return found


def _image_nodes(
    index: int,
    heading_id: str | None,
    image_runs: list[tuple[int, EmbeddedImage]],
) -> list[tuple[Node, RunSpan | None]]:
    single = len(image_runs) == 1
    out: list[tuple[Node, RunSpan | None]] = []
    for k, (run_index, image) in enumerate(image_runs):
        node_id = f"p{index}" if single else f"p{index}.i{k}"
        node = Node(
            id=node_id,
            kind="image",
            text="",
            parent_id=heading_id,
            image_sha256=image.sha256,
        )
        span = RunSpan(paragraph_index=index, run_start=run_index, run_end=run_index)
        out.append((node, span))
    return out


def _table_cell_nodes(table: Table, table_index: int) -> list[Node]:
    """One node per grid cell. `RunSpan` cannot address a table-cell paragraph — its
    `paragraph_index` indexes `Document.paragraphs`, which excludes paragraphs nested in
    table cells by construction (`CT_Body.p_lst` is direct `<w:p>` children only) — so
    these nodes exist for identity and never appear in a `RenderMap`. A comment anchored to
    one falls back to the document-level anchor in `attach_comments`.

    A merged cell is returned once per grid position it spans (python-docx's own
    behaviour), so two ids can carry identical text. That is a duplicate of content, not
    of id — every id here is still a distinct, stable position.
    """
    nodes: list[Node] = []
    for ri, row in enumerate(table.rows):
        for ci, cell in enumerate(row.cells):
            nodes.append(
                Node(
                    id=f"t{table_index}.r{ri}.c{ci}",
                    kind="table_cell",
                    text=cell.text.strip(),
                    parent_id=None,
                )
            )
    return nodes
