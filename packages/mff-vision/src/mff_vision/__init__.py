"""Client contract for image understanding (req 13).

Image understanding is a separate service, owned separately. This package holds the
contract the editor calls through, an HTTP client for that service, and a deterministic
in-process stand-in for tests and evals.
"""

from .client import HttpVisionTool
from .mock import InventoryVisionTool
from .models import (
    UNKNOWN,
    Constraint,
    ImageAnalysis,
    ImageRef,
    RequirementSpec,
    VisionTool,
    VisionUnavailable,
)

__all__ = [
    "UNKNOWN",
    "Constraint",
    "HttpVisionTool",
    "ImageAnalysis",
    "ImageRef",
    "InventoryVisionTool",
    "RequirementSpec",
    "VisionTool",
    "VisionUnavailable",
]
