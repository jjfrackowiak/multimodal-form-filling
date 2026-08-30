"""CV tool: checklist + photos → inventory.

Production path is HTTP (`CvClient` / POST /v1/inventory). `build_inventory`
is the same logic in-process for the CLI and tests.
"""

from cv.client import CvClient, CvError
from cv.pipeline import build_inventory
from cv.schema import (
    Finding,
    ImageLabel,
    ImageRef,
    Inventory,
    InventoryImage,
    InventoryRequest,
    InventoryResponse,
    ParsedChecklist,
    Requirement,
)

__all__ = [
    "CvClient",
    "CvError",
    "Finding",
    "ImageLabel",
    "ImageRef",
    "Inventory",
    "InventoryImage",
    "InventoryRequest",
    "InventoryResponse",
    "ParsedChecklist",
    "Requirement",
    "build_inventory",
]
