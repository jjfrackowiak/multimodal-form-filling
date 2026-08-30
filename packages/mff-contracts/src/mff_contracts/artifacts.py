"""Artifacts — one per job — req 12.

`schema_version` matters because these persist: Firestore documents outlive deploys, and an
in-flight job loaded after a shape change must fail loudly rather than parse partially. The
field enforces `>= 1` so a missing/zero version is a validation error, not a silent gap.
"""

from __future__ import annotations

from typing import TypeAlias

from pydantic import BaseModel, Field

from .blobs import BlobRef
from .docmodel import FormDraft, Node
from .review import ReviewComment

__all__ = ["Artifact", "DerivativeArtifact", "NetNewArtifact"]


class DerivativeArtifact(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    form_id: str
    source: BlobRef  # immutable
    nodes: list[Node] = Field(default_factory=list)
    comments: list[ReviewComment] = Field(default_factory=list)


class NetNewArtifact(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    form_id: str
    draft: FormDraft
    comments: list[ReviewComment] = Field(default_factory=list)


Artifact: TypeAlias = DerivativeArtifact | NetNewArtifact
