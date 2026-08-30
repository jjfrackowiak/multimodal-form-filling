"""The seam between the editor and image understanding (req 13).

This package contains no image processing and never will. Image understanding is a
**separate service**, owned separately (see AGENTS.md). What lives here is the contract
the editor calls through, plus a deterministic stand-in so the editor can be built and
evaluated before that service exists.

One operation, not three. The service is told **what is being looked for** and answers
with an inventory of **what each image actually shows**:

    requirements + images  ->  inventory

That shape matters. A generic "describe this image" call cannot know whether
"between the front seats" is a meaningful distinction or an irrelevant detail, so it
would invent its own vocabulary and leave the editor to reconcile it. Given the
requirements, the service knows what it is discriminating between.

Because the real implementation is remote, the contract is shaped for a network call:
async, images named by URI so the service fetches them itself, and one round trip per
job rather than per image.

`ImageAnalysis`, `RequirementSpec` and `Constraint` are wire types shared with the editor
and are defined in `mff_contracts`, not here — this module re-exports them so nothing
downstream notices. `ImageRef` and `VisionTool` stay local: they are this client's
concern, not the frozen contract's.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from mff_contracts import Constraint, ImageAnalysis, RequirementSpec

__all__ = [
    "UNKNOWN",
    "Constraint",
    "ImageAnalysis",
    "ImageRef",
    "RequirementSpec",
    "VisionTool",
    "VisionUnavailable",
]

UNKNOWN = "unknown"


class VisionUnavailable(RuntimeError):
    """The vision service could not be reached or refused the request.

    Distinct from an image the service looked at and could not identify — that comes back
    as an ImageAnalysis with `depicts == UNKNOWN`. Treat this one as infrastructure
    failure and the other as evidence: an unreachable service must never be recorded as a
    finding about the client's photographs.
    """


class ImageRef(BaseModel):
    """How an image is named across the wire.

    A URI the service can resolve for itself (`gs://bucket/...`), so the editor never
    ships pixels. A bare filename is accepted for tests and for the stand-in, where there
    is no bucket.
    """

    uri: str

    @property
    def name(self) -> str:
        """Basename, which is how humans and the fixture refer to an image."""
        return self.uri.rsplit("/", 1)[-1]


@runtime_checkable
class VisionTool(Protocol):
    """One operation. The editor calls it; it never calls the editor."""

    async def build_inventory(
        self,
        images: list[ImageRef],
        requirements: list[RequirementSpec],
    ) -> list[ImageAnalysis]:
        """Classify every image against what the requirements are looking for.

        Called **once per job at ingest**, not inside slices: the result is deterministic
        per image, so every slice then reasons from identical image facts and cannot reach
        different conclusions because the service answered differently.

        The result is index-aligned with `images`.
        """
        ...
