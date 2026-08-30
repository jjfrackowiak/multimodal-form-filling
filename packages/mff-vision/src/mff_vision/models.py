"""The seam between the editor and image understanding (req 13).

This package contains no image processing and never will. Image understanding is
a **separate service**, owned separately (see AGENTS.md). What lives here is the
contract the editor calls through, plus a deterministic stand-in so the editor
can be built and evaluated before that service exists.

Because the real implementation is remote, the contract is shaped for a network
call rather than a library call:

  * every operation is async
  * images are named by URI, not by local path — the service fetches them itself
  * `describe_many` exists so a document's worth of photographs is one round trip
  * a result can be unknown; that is an answer, not an exception
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

__all__ = [
    "UNKNOWN",
    "BoundingBox",
    "ImageAnalysis",
    "ImageRef",
    "VisionTool",
    "VisionUnavailable",
]

UNKNOWN = "unknown"


class VisionUnavailable(RuntimeError):
    """The vision service could not be reached or refused the request.

    Distinct from an image the service looked at and could not identify — that
    comes back as an ImageAnalysis with `depicts == UNKNOWN`. A caller should
    treat this one as infrastructure failure and the other as evidence.
    """


class ImageRef(BaseModel):
    """How an image is named across the wire.

    A URI the vision service can resolve for itself (`gs://bucket/...`), so the
    editor never ships pixels. A bare filename is accepted for tests and for the
    mock, where there is no bucket.
    """

    uri: str

    @property
    def name(self) -> str:
        """Basename, which is how humans and the fixture refer to an image."""
        return self.uri.rsplit("/", 1)[-1]


class BoundingBox(BaseModel):
    """Normalised 0..1 coordinates, so a crop survives resizing."""

    left: float = Field(ge=0.0, le=1.0)
    top: float = Field(ge=0.0, le=1.0)
    right: float = Field(ge=0.0, le=1.0)
    bottom: float = Field(ge=0.0, le=1.0)


class ImageAnalysis(BaseModel):
    """What the editor needs to know about one photograph.

    `depicts` answers "what is this a picture of". `shot_from` answers "from
    where", which is a different question and the one that decides R-04 in the
    fleet fixture: two photographs both depict the headliner, and only one is
    taken from between the front seats.
    """

    file: str
    depicts: str
    shot_from: str | None = None
    note: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def is_known(self) -> bool:
        return self.depicts != UNKNOWN


@runtime_checkable
class VisionTool(Protocol):
    """Three operations, no configuration, no state.

    The editor calls it; it never calls the editor.
    """

    async def describe(self, ref: ImageRef) -> ImageAnalysis:
        """Identify a single image."""
        ...

    async def describe_many(self, refs: list[ImageRef]) -> list[ImageAnalysis]:
        """Identify several. The result is index-aligned with the input.

        One call per document rather than per photograph: the fleet fixture has
        seventeen, and seventeen round trips to another service is the difference
        between a slice that fits its latency budget and one that does not.
        """
        ...

    async def crop(self, ref: ImageRef, box: BoundingBox) -> ImageRef:
        """Produce a cropped derivative and return a reference to it."""
        ...
