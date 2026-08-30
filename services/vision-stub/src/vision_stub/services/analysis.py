"""Business logic. Imports no web framework — see the plan's service structure.

That rule is what lets this be exercised from a test with no server running, and
it is why the real service can replace this one without the editor noticing.
"""

from __future__ import annotations

from pathlib import Path

from ffx_vision import BoundingBox, ImageAnalysis, ImageRef, InventoryVisionTool

__all__ = ["AnalysisService"]


class AnalysisService:
    """Placeholder implementation: answers from the golden inventory.

    Michal's service replaces this module. Everything else — the routes, the
    payload shapes, the client, the editor — stays exactly as it is.
    """

    def __init__(self, inventory_path: Path | None = None) -> None:
        self._tool = InventoryVisionTool(inventory_path)

    async def describe(self, ref: ImageRef) -> ImageAnalysis:
        return await self._tool.describe(ref)

    async def describe_many(self, refs: list[ImageRef]) -> list[ImageAnalysis]:
        return await self._tool.describe_many(refs)

    async def crop(self, ref: ImageRef, box: BoundingBox) -> ImageRef:
        return await self._tool.crop(ref, box)
