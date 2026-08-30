"""Embedded media — extracting the bytes behind an inline `<w:drawing>`.

`Node.image_sha256` links an embedded image to its `JobImage`, so this is the one place in
the package that reaches for Pillow: not to transform anything (no crop, no resize — that
was dropped from scope, see `mff_contracts.blobs`), but to refuse to mint an "image" node
for a `<w:drawing>` that turns out not to be a decodable raster image (a chart, a shape,
some other drawingML content with no `a:blip`, or a corrupt part). Better to fall back to
treating the paragraph as text than to publish a node whose `image_sha256` points at bytes
that are not a photograph.
"""

from __future__ import annotations

import hashlib
import io
from typing import TYPE_CHECKING

from docx.oxml.ns import qn
from PIL import Image, UnidentifiedImageError

if TYPE_CHECKING:
    from docx.document import Document as DocxDocument
    from docx.oxml.text.run import CT_R

__all__ = ["EmbeddedImage", "embedded_images_in_run"]

# python-docx's custom lxml parser class registers these namespace prefixes globally, so
# a prefixed xpath resolves without an explicit `namespaces=` map (and Clark-notation
# `{uri}local` paths, which would otherwise be the safer choice, are *not* accepted by
# lxml's XPath 1.0 engine as a path segment — verified against this exact element).
_BLIP_XPATH = ".//a:blip"
_R_EMBED = qn("r:embed")


class EmbeddedImage:
    """One `<a:blip>` found in a run, resolved to real bytes and their sha256."""

    __slots__ = ("blob", "sha256")

    def __init__(self, blob: bytes, sha256: str) -> None:
        self.blob = blob
        self.sha256 = sha256


def embedded_images_in_run(run_element: CT_R, document: DocxDocument) -> list[EmbeddedImage]:
    """Every valid raster image referenced by `<a:blip>` elements inside one run.

    Order matches document order (there is normally exactly one; a run with several is
    handled the same way). A `<a:blip>` that does not resolve to a decodable image —
    dangling relationship id, non-raster part — is skipped rather than raising: a form
    author's odd drawing should not break parsing the rest of the document.
    """
    found: list[EmbeddedImage] = []
    for blip in run_element.xpath(_BLIP_XPATH):
        rid = blip.get(_R_EMBED)
        if not rid:
            continue
        image = _resolve(rid, document)
        if image is not None:
            found.append(image)
    return found


def _resolve(rid: str, document: DocxDocument) -> EmbeddedImage | None:
    try:
        part = document.part.related_parts[rid]
    except KeyError:
        return None
    blob: bytes = part.blob
    if not _is_decodable_image(blob):
        return None
    return EmbeddedImage(blob=blob, sha256=hashlib.sha256(blob).hexdigest())


def _is_decodable_image(blob: bytes) -> bool:
    try:
        with Image.open(io.BytesIO(blob)) as im:
            im.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        return False
    return True
