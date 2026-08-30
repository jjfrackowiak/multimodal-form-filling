"""Bytes in, bytes out. `python-docx` only speaks file-like objects."""

from __future__ import annotations

import io

from docx import Document as _Document
from docx.document import Document as DocxDocument

__all__ = ["dump_document", "load_document"]


def load_document(data: bytes) -> DocxDocument:
    return _Document(io.BytesIO(data))


def dump_document(document: DocxDocument) -> bytes:
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()
