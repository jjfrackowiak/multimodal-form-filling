"""Blobs and images — req 13.

`ImageAnalysis` and `RequirementSpec` live here rather than in `mff-vision`: both are wire
types shared by the vision service and the editor, and owning them in a service client
package would make this frozen package depend on that client. `mff-vision` imports them
from here.

No `BoundingBox` and no cropping. An earlier draft carried a crop operation; nothing in the
flow needs it, so it was removed from scope (see the plan, "Cropping is out of scope").
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["BlobRef", "ImageAnalysis", "JobImage", "RequirementSpec"]


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
    `text`, the verbatim `source_span`, and `constraint`. It has no business knowing
    manifest offsets (`ordinal` / `source_line`), slice scopes, or `applies_to`.

    `source_span` is the client's own wording. Vision uses it as the look-for when every
    requirement already has an id and a span, so the raw manifest does not also have to
    be sent. Empty means "not available; pass the raw manifest if the service needs it".
    """

    id: str
    text: str
    source_span: str = ""  # VERBATIM substring of Manifest.raw
    constraint: str | None = None  # e.g. "camera position: between_front_seats"


class ImageAnalysis(BaseModel):
    """What one photograph actually shows.

    `depicts` answers "what is this a picture of". `shot_from` answers "from where", a
    separate question — merging the two would lose the distinction that decides R-04 in the
    fleet fixture, where two headliner photographs are told apart only by camera position.
    """

    file: str
    depicts: str  # "headliner", "seat_front", … or "unknown"
    shot_from: str | None = None  # "between_front_seats" — a SEPARATE question
    note: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def is_known(self) -> bool:
        return self.depicts != "unknown"


class JobImage(BaseModel):
    """One image as it travels with a job, with its vision analysis cached at ingest."""

    blob: BlobRef
    original_filename: str
    source: Literal["attachment", "embedded"]  # loose file, or pulled from a .docx
    analysis: ImageAnalysis | None = None  # cached at ingest, keyed by sha256
