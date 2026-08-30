"""The stand-in must be right about the case the fixture exists to catch."""

from __future__ import annotations

import pytest

from mff_vision import (
    UNKNOWN,
    Constraint,
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
        constraint=Constraint(
            kind="camera_position",
            value="between_front_seats",
            source_span="Podsufitka trzeba spomiędzy forteli zrobić",
            source_line=10,
        ),
    )
]


@pytest.fixture
def tool() -> InventoryVisionTool:
    return InventoryVisionTool()


async def test_satisfies_the_protocol(tool: InventoryVisionTool) -> None:
    assert isinstance(tool, VisionTool)


async def test_headliners_differ_by_camera_position(tool: InventoryVisionTool) -> None:
    """R-04: both depict the headliner, only one is shot from between the seats.

    If this ever collapses to one answer, a derivative run would pass R-04 for the wrong
    reason and the fixture's whole point would be lost.
    """
    good, bad = await tool.build_inventory(
        [ImageRef(uri=CORRECT_HEADLINER), ImageRef(uri=WRONG_HEADLINER)], REQS
    )
    assert good.depicts == bad.depicts == "headliner"
    assert good.shot_from == "between_front_seats"
    assert bad.shot_from == "beside_seat"
    assert good.shot_from != bad.shot_from


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
    assert out[0].depicts == "headliner"


async def test_duplicate_files_resolve_to_the_same_label(tool: InventoryVisionTool) -> None:
    """The submission delivered two byte-identical pairs; both names must answer."""
    a, b = await tool.build_inventory(
        [ImageRef(uri="1000040429.jpg"), ImageRef(uri="IMG_20260830_132755 (8).jpg")],
        REQS,
    )
    assert a.depicts == b.depicts == "boot"


async def test_unknown_image_is_evidence_not_an_error(tool: InventoryVisionTool) -> None:
    out = await tool.build_inventory([ImageRef(uri="mystery.jpg")], REQS)
    assert out[0].depicts == UNKNOWN
    assert out[0].confidence == 0.0
    assert out[0].is_known is False


async def test_empty_request_is_an_empty_inventory(tool: InventoryVisionTool) -> None:
    assert await tool.build_inventory([], REQS) == []


async def test_every_inventory_entry_is_reachable(tool: InventoryVisionTool) -> None:
    """A label nothing can look up is a label that does not exist."""
    refs = [ImageRef(uri=n) for n in tool._by_name]
    out = await tool.build_inventory(refs, REQS)
    assert all(a.is_known for a in out)


def test_analysis_rejects_impossible_confidence() -> None:
    with pytest.raises(ValueError):
        ImageAnalysis(file="x.jpg", depicts="boot", confidence=1.5)


def test_requirement_spec_is_a_projection() -> None:
    """The service gets what it can act on — not manifest offsets or slice scopes."""
    fields = set(RequirementSpec.model_fields)
    assert fields == {"id", "text", "constraint"}
    assert "ordinal" not in fields and "source_span" not in fields
