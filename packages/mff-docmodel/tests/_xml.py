"""Shared XML helpers for the byte-identical-body tests.

Not part of the package's public surface — these exist purely to let a test compare
`word/document.xml` before and after with the comment markup surgically removed.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def read_document_xml(docx_bytes: bytes) -> bytes:
    with zipfile.ZipFile(BytesIO(docx_bytes)) as archive:
        return archive.read("word/document.xml")


def canonical(xml_bytes: bytes) -> bytes:
    """Re-serialise through the same lxml pipeline so two logically-equal documents that
    merely differ in how they were produced compare equal byte-for-byte."""
    root = etree.fromstring(xml_bytes)
    result: bytes = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return result


def strip_comment_ranges(xml_bytes: bytes) -> bytes:
    """Remove every trace of comment anchoring: `commentRangeStart`/`commentRangeEnd`
    markers, and the whole `<w:r>` run `Document.add_comment` inserts to hold the
    `commentReference`. What is left is the body as it would read with zero comments."""
    root = etree.fromstring(xml_bytes)
    for tag in ("commentRangeStart", "commentRangeEnd"):
        for el in root.iter(f"{{{W_NS}}}{tag}"):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
    for ref in root.iter(f"{{{W_NS}}}commentReference"):
        run = ref.getparent()
        if run is not None and run.tag == f"{{{W_NS}}}r":
            parent = run.getparent()
            if parent is not None:
                parent.remove(run)
    result: bytes = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return result
