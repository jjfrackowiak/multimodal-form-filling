"""HTTP request and response shapes.

The models themselves come from `mff_vision` — they are the wire contract, and the
service must not define a second, drifting copy of them.
"""

from __future__ import annotations

from pydantic import BaseModel

from mff_vision import ImageAnalysis, ImageRef, RequirementSpec

__all__ = ["InventoryRequest", "InventoryResponse"]


class InventoryRequest(BaseModel):
    images: list[ImageRef]
    requirements: list[RequirementSpec]


class InventoryResponse(BaseModel):
    images: list[ImageAnalysis]  # index-aligned with the request
