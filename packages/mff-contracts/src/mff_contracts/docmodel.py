"""Document models — one per mode — reqs 12, 14, 15.

`Node` is the derivative, read-only view of the client's supplied document: it never
changes, so its ids are stable. `Entry`/`Section`/`FormDraft` build a net-new document from
nothing; `DraftOp` is how an agent grows one, because replace alone cannot build a
document — an agent needs to append new entries, not just overwrite existing ones.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from .blobs import BlobRef

__all__ = ["DraftOp", "Entry", "FormDraft", "Node", "Section"]


class Node(BaseModel):
    """DERIVATIVE: a read-only view of one piece of the client's document."""

    id: str  # stable because the document never changes
    kind: Literal["heading", "paragraph", "table_cell", "image", "caption"]
    text: str
    parent_id: str | None = None
    image_sha256: str | None = None  # links an embedded image to its JobImage


class Entry(BaseModel):
    """NET-NEW: one value an agent has written into the draft."""

    id: str  # minted on append; never positional
    order: str  # fractional index — insertion renumbers nothing
    value: str | None = None
    images: list[BlobRef] = Field(default_factory=list)
    set_by: str  # requirement id that produced it


class Section(BaseModel):
    id: str
    title: str
    entries: list[Entry] = Field(default_factory=list)


class FormDraft(BaseModel):
    schema_version: int = 1
    sections: list[Section] = Field(default_factory=list)


class DraftOp(BaseModel):
    """One mutation to a `FormDraft`. `replace` alone cannot build a document."""

    kind: Literal["set", "append", "delete"]
    requirement_id: str
    section_id: str | None = None  # append
    entry_id: str | None = None  # set, delete
    value: str | None = None
    images: list[BlobRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fields_match_kind(self) -> Self:
        if self.kind == "append":
            if not self.section_id:
                raise ValueError("DraftOp(kind='append') requires section_id")
            if self.entry_id is not None:
                raise ValueError("DraftOp(kind='append') must not set entry_id")
        else:  # "set", "delete"
            if not self.entry_id:
                raise ValueError(f"DraftOp(kind={self.kind!r}) requires entry_id")
            if self.section_id is not None:
                raise ValueError(f"DraftOp(kind={self.kind!r}) must not set section_id")
        return self
