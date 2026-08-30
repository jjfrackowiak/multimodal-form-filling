"""Client contract for image understanding (req 13).

Image understanding is a separate service, owned separately. This package holds
the contract the editor calls through, an HTTP client for the real service, and a
deterministic in-process stand-in for tests and evals.
"""

from .client import HttpVisionTool
from .mock import InventoryVisionTool
from .models import (
    UNKNOWN,
    BoundingBox,
    ImageAnalysis,
    ImageRef,
    VisionTool,
    VisionUnavailable,
)

__all__ = [
    "UNKNOWN",
    "BoundingBox",
    "HttpVisionTool",
    "ImageAnalysis",
    "ImageRef",
    "InventoryVisionTool",
    "VisionTool",
    "VisionUnavailable",
]
