"""Compile — the typed output.

`python-docx` needs *runs*; we hold ids. `RenderMap` is the bridge, built during compile
when the renderer knows exactly where each node or entry landed. `unanchored` makes the
document-level fallback visible: if requirements land there routinely, region scoping is
not working.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .blobs import BlobRef

__all__ = ["CompiledForm", "RenderMap", "RunSpan"]


class RunSpan(BaseModel):
    """How an anchor id becomes actual runs."""

    paragraph_index: int
    run_start: int
    run_end: int  # inclusive


class RenderMap(BaseModel):
    anchor_to_span: dict[str, RunSpan] = Field(default_factory=dict)  # Node.id/Entry.id -> span


class CompiledForm(BaseModel):
    form_id: str
    document: BlobRef
    render_map: RenderMap
    comments_attached: int
    unanchored: list[str] = Field(default_factory=list)  # requirement ids that fell back
