"""Business logic. Imports no web framework — see the plan's service structure.

That rule is what lets this be exercised from a test with no server running, and it is why
the real service can replace this one without the editor noticing.
"""

from __future__ import annotations

from pathlib import Path

from mff_vision import ImageAnalysis, ImageRef, InventoryVisionTool, RequirementSpec

__all__ = ["AnalysisService"]


class AnalysisService:
    """Placeholder implementation: answers from the golden inventory.

    Michal's service replaces this module. Everything else — the route, the payload
    shapes, the client, the editor — stays exactly as it is.
    """

    def __init__(self, inventory_path: Path | None = None) -> None:
        self._tool = InventoryVisionTool(inventory_path)

    async def build_inventory(
        self,
        images: list[ImageRef],
        requirements: list[RequirementSpec],
    ) -> list[ImageAnalysis]:
        return await self._tool.build_inventory(images, requirements)
