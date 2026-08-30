"""HTTP request shapes. Responses reuse the ffx_vision models directly, which are
the wire contract — see the plan: contracts and HTTP schemas do not leak."""

from __future__ import annotations

from ffx_vision import BoundingBox, ImageRef
from pydantic import BaseModel

__all__ = ["BatchRequest", "CropRequest", "DescribeRequest"]


class DescribeRequest(BaseModel):
    ref: ImageRef


class BatchRequest(BaseModel):
    refs: list[ImageRef]


class CropRequest(BaseModel):
    ref: ImageRef
    box: BoundingBox
