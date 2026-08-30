"""The stand-in must be right about the case the fixture exists to catch."""

from __future__ import annotations

import pytest

from mff_vision import (
    ImageAnalysis,
    ImageRef,
    InventoryVisionTool,
    RequirementSpec,
    VisionTool,
)

CORRECT_HEADLINER = "1000040420.jpg"
WRONG_HEADLINER = "IMG_20260830_132755 (5).jpg"

REQS = [
    RequirementSpec(
        id="R-04",
        text="Two photographs of the headliner.",
        constraint="camera position: between_front_seats",
    )
]


def _hit(row: ImageAnalysis, rid: str):
    return next(h for h in row.hits if h.id == rid)


@pytest.fixture
def tool() -> InventoryVisionTool:
    return InventoryVisionTool()


async def test_satisfies_the_protocol(tool: InventoryVisionTool) -> None:
    assert isinstance(tool, VisionTool)


async def test_headliners_differ_by_camera_position(tool: InventoryVisionTool) -> None:
    """R-04: both hit the headliner id, only one satisfies the pose constraint."""
    good, bad = await tool.build_inventory(
        [ImageRef(uri=CORRECT_HEADLINER), ImageRef(uri=WRONG_HEADLINER)], REQS
    )
    assert [h.id for h in good.hits] == [h.id for h in bad.hits] == ["R-04"]
    assert _hit(good, "R-04").constraint_ok is True
    assert _hit(bad, "R-04").constraint_ok is False


async def test_result_is_index_aligned(tool: InventoryVisionTool) -> None:
    """The editor matches analyses back to images by position; drift here is silent."""
    refs = [
        ImageRef(uri=CORRECT_HEADLINER),
        ImageRef(uri="not-in-the-submission.jpg"),
        ImageRef(uri=WRONG_HEADLINER),
    ]
    out = await tool.build_inventory(refs, REQS)
    assert [a.file for a in out] == [r.name for r in refs]


async def test_resolves_a_gs_uri_by_basename(tool: InventoryVisionTool) -> None:
    ref = ImageRef(uri=f"gs://bucket/jobs/abc/images/{CORRECT_HEADLINER}")
    assert ref.name == CORRECT_HEADLINER
    out = await tool.build_inventory([ref], REQS)
    assert [h.id for h in out[0].hits] == ["R-04"]


async def test_duplicate_files_resolve_to_the_same_label(tool: InventoryVisionTool) -> None:
    """The submission delivered two byte-identical pairs; both names must answer."""
    a, b = await tool.build_inventory(
        [ImageRef(uri="1000040429.jpg"), ImageRef(uri="IMG_20260830_132755 (8).jpg")],
        REQS,
    )
    assert [h.id for h in a.hits] == [h.id for h in b.hits] == ["R-08"]


async def test_unknown_image_is_evidence_not_an_error(tool: InventoryVisionTool) -> None:
    out = await tool.build_inventory([ImageRef(uri="mystery.jpg")], REQS)
    assert out[0].hits == []
    assert out[0].is_known is False


async def test_empty_request_is_an_empty_inventory(tool: InventoryVisionTool) -> None:
    assert await tool.build_inventory([], REQS) == []


async def test_every_inventory_entry_is_reachable(tool: InventoryVisionTool) -> None:
    """A label nothing can look up is a label that does not exist."""
    refs = [ImageRef(uri=n) for n in tool._by_name]
    out = await tool.build_inventory(refs, REQS)
    assert all(a.is_known for a in out)


def test_requirement_spec_is_a_projection() -> None:
    """The service gets the look-for fields, not editor bookkeeping."""
    fields = set(RequirementSpec.model_fields)
    assert fields == {"id", "text", "constraint"}
    assert "ordinal" not in fields and "source_span" not in fields
