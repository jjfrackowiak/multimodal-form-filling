"""Blobs and images — req 13.

`ImageAnalysis` and `RequirementSpec` live here rather than in `mff-vision`: both are wire
types shared by the vision service and the editor, and owning them in a service client
package would make this frozen package depend on that client. `mff-vision` imports them
from here.

No `BoundingBox` and no cropping. An earlier draft carried a crop operation; nothing in the
flow needs it, so it was removed from scope (see the plan, "Cropping is out of scope").
The service looks for `RequirementSpec.text`, not a frozen `depicts` vocabulary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .requirements import Constraint

__all__ = [
    "BlobRef",
    "Finding",
    "ImageAnalysis",
    "JobImage",
    "RequirementHit",
    "RequirementSpec",
]


class BlobRef(BaseModel):
    """A content-addressed pointer to bytes in the blob store.

    Content-addressing (`sha256`) collapses duplicates at ingest and makes retries safe.
    """

    uri: str  # gs://<bucket>/jobs/<job_id>/<kind>/<sha256>
    content_type: str
    size_bytes: int
    sha256: str


class RequirementSpec(BaseModel):
    """What the vision service is looking for.

    A deliberate **projection** of `Requirement`, not a copy. The service receives `id`,
    `text` and `constraint`; it has no business knowing manifest offsets, slice scopes or
    `applies_to`. `constraint` carries the same structured `Constraint` as `Requirement`
    rather than a re-flattened string, so the service and the editor agree on one shape
    for `kind`/`value` instead of each having to parse or invent an encoding.
    """

    id: str
    text: str
    constraint: Constraint | None = None


class RequirementHit(BaseModel):
    """One checklist id this photograph actually supports."""

    id: str
    constraint_ok: bool | None = None
    constraint_evidence: str | None = None


class Finding(BaseModel):
    """A visible detail that is not a frozen form field."""

    what: str
    value: str
    evidence: str = ""


class ImageAnalysis(BaseModel):
    """What one photograph actually shows, against the requirements it was given.

    `hits` are checklist ids this frame supports. A constraint is per-id
    (`constraint_ok`), which is how two headliner photos can share R-04 and still
    disagree on "shot from between the front seats".
    An image the service looked at and could not place comes back with empty hits —
    evidence, not an error.
    """

    file: str
    uri: str | None = None
    hits: list[RequirementHit] = Field(default_factory=list)
    note: str | None = None
    findings: list[Finding] = Field(default_factory=list)
    exact_duplicate_of: str | None = None

    @property
    def is_known(self) -> bool:
        return bool(self.hits)


class JobImage(BaseModel):
    """One image as it travels with a job, with its vision analysis cached at ingest."""

    blob: BlobRef
    original_filename: str
    source: Literal["attachment", "embedded"]  # loose file, or pulled from a .docx
    analysis: ImageAnalysis | None = None  # cached at ingest, keyed by sha256
