"""HTTP request and response shapes.

The models themselves come from `mff_vision` — they are the wire contract, and the
service must not define a second, drifting copy of them.
"""

from __future__ import annotations

from mff_vision import ImageAnalysis, ImageRef, RequirementSpec
from pydantic import BaseModel

__all__ = ["InventoryRequest", "InventoryResponse"]


class InventoryRequest(BaseModel):
    images: list[ImageRef]
    requirements: list[RequirementSpec]


class InventoryResponse(BaseModel):
    images: list[ImageAnalysis]     # index-aligned with the request
