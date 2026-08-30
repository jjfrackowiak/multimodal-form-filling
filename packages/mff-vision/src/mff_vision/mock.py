"""A deterministic stand-in for the vision service.

Answers from the fixture's `inventory.yaml` — the human-labelled ground truth for what
each photograph shows. Two consequences worth being explicit about:

  * **It is a lookup, not a guess.** Each image gets its own correct label, so the editor
    exercises real branching. In particular the two headliner photographs return different
    `shot_from` values, which is what lets a derivative run fail R-04 for the right reason
    instead of by luck.
  * **It cannot be wrong.** That makes it useless for measuring vision quality and ideal
    for everything else: the editor and the evals become fully deterministic, so a failing
    test means the editor is broken, never that a model had an off day.

When the real service lands, the same `inventory.yaml` becomes the answer key it is scored
against — which is exactly the shape of this interface: requirements in, inventory out.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .models import UNKNOWN, ImageAnalysis, ImageRef, RequirementSpec

__all__ = ["InventoryVisionTool", "default_inventory"]

ENV_VAR = "MFF_VISION_INVENTORY"
_RELATIVE = Path("fixtures") / "fleet-vehicle-return" / "inventory.yaml"


def default_inventory() -> Path:
    """Locate the labelled inventory.

    Explicit env var first, then a walk up from this file. The walk exists because the
    stand-in is bound to a fixture living outside the package: installed as a wheel there
    is no fixed relative path to it, so guessing a parent depth is wrong sooner or later.
    It was wrong the first time.
    """
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _RELATIVE
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[-1] / _RELATIVE


class InventoryVisionTool:
    """In-process `VisionTool` backed by a labelled inventory file."""

    def __init__(self, inventory_path: Path | None = None) -> None:
        path = inventory_path or default_inventory()
        if not path.exists():
            raise FileNotFoundError(
                f"inventory not found: {path}. Set {ENV_VAR} to point at "
                "fixtures/fleet-vehicle-return/inventory.yaml"
            )
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self._by_name: dict[str, ImageAnalysis] = {
            entry["file"]: ImageAnalysis(
                file=entry["file"],
                depicts=entry["depicts"],
                shot_from=entry.get("shot_from"),
                note=entry.get("note"),
            )
            for entry in data["images"]
        }
        # Files the submission duplicated share a label with their twin, so a lookup on
        # either name resolves rather than returning unknown.
        for entry in data["images"]:
            twin = entry.get("exact_duplicate_of")
            if twin:
                self._by_name[twin] = self._by_name[entry["file"]].model_copy(update={"file": twin})

    async def build_inventory(
        self,
        images: list[ImageRef],
        requirements: list[RequirementSpec],
    ) -> list[ImageAnalysis]:
        # `requirements` is ignored here and that is the honest behaviour: the answer key
        # was written by a human who already knew what was being looked for. The real
        # service will use it to decide what it is discriminating between.
        return [self._one(ref) for ref in images]

    def _one(self, ref: ImageRef) -> ImageAnalysis:
        known = self._by_name.get(ref.name)
        if known is None:
            # An unrecognised image is evidence, not an error. The editor has to decide
            # what an unidentifiable photograph means for a requirement.
            return ImageAnalysis(file=ref.name, depicts=UNKNOWN, confidence=0.0)
        return known
