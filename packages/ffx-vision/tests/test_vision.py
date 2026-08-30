"""The mock must be right about the case the fixture exists to catch."""

from __future__ import annotations

import pytest

from ffx_vision import UNKNOWN, BoundingBox, ImageAnalysis, ImageRef, InventoryVisionTool

CORRECT_HEADLINER = "1000040420.jpg"
WRONG_HEADLINER = "IMG_20260830_132755 (5).jpg"


@pytest.fixture
def tool() -> InventoryVisionTool:
    return InventoryVisionTool()


async def test_satisfies_the_protocol(tool: InventoryVisionTool) -> None:
    from ffx_vision import VisionTool

    assert isinstance(tool, VisionTool)


async def test_headliners_differ_by_camera_position(tool: InventoryVisionTool) -> None:
    """R-04: both depict the headliner, only one is shot from between the seats.

    If this ever collapses to one answer, a derivative run would pass R-04 for
    the wrong reason and the fixture's whole point would be lost.
    """
    good = await tool.describe(ImageRef(uri=CORRECT_HEADLINER))
    bad = await tool.describe(ImageRef(uri=WRONG_HEADLINER))

    assert good.depicts == bad.depicts == "headliner"
    assert good.shot_from == "between_front_seats"
    assert bad.shot_from == "beside_seat"
    assert good.shot_from != bad.shot_from


async def test_resolves_a_gs_uri_by_basename(tool: InventoryVisionTool) -> None:
    ref = ImageRef(uri=f"gs://bucket/jobs/abc/images/{CORRECT_HEADLINER}")
    assert ref.name == CORRECT_HEADLINER
    assert (await tool.describe(ref)).depicts == "headliner"


async def test_duplicate_files_resolve_to_the_same_label(tool: InventoryVisionTool) -> None:
    """The submission delivered two byte-identical pairs; both names must answer."""
    a = await tool.describe(ImageRef(uri="1000040429.jpg"))
    b = await tool.describe(ImageRef(uri="IMG_20260830_132755 (8).jpg"))
    assert a.depicts == b.depicts == "boot"


async def test_unknown_image_is_evidence_not_an_error(tool: InventoryVisionTool) -> None:
    result = await tool.describe(ImageRef(uri="not-in-the-submission.jpg"))
    assert result.depicts == UNKNOWN
    assert result.confidence == 0.0
    assert result.is_known is False


async def test_batch_is_index_aligned(tool: InventoryVisionTool) -> None:
    refs = [ImageRef(uri=CORRECT_HEADLINER), ImageRef(uri="nope.jpg"), ImageRef(uri=WRONG_HEADLINER)]
    out = await tool.describe_many(refs)
    assert [a.file for a in out] == [r.name for r in refs]


async def test_crop_returns_a_distinguishable_ref(tool: InventoryVisionTool) -> None:
    box = BoundingBox(left=0.1, top=0.2, right=0.8, bottom=0.9)
    out = await tool.crop(ImageRef(uri=CORRECT_HEADLINER), box)
    assert out.uri != CORRECT_HEADLINER
    assert "crop=" in out.uri


async def test_every_inventory_entry_is_reachable(tool: InventoryVisionTool) -> None:
    """A label nothing can look up is a label that does not exist."""
    for name in tool._by_name:
        assert (await tool.describe(ImageRef(uri=name))).is_known


def test_analysis_rejects_impossible_confidence() -> None:
    with pytest.raises(ValueError):
        ImageAnalysis(file="x.jpg", depicts="boot", confidence=1.5)
