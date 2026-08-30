"""Round-trip the real client against the real service over real HTTP.

Proves the two halves agree. Without this they can drift apart and nothing notices until
the real service arrives and the payload shapes turn out never to have matched.
"""

from __future__ import annotations

import httpx
import pytest

from mff_vision import Constraint, HttpVisionTool, ImageRef, RequirementSpec, VisionUnavailable
from vision_stub.main import create_app

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
def vision() -> HttpVisionTool:
    transport = httpx.ASGITransport(app=create_app())
    client = httpx.AsyncClient(transport=transport, base_url="http://vision")
    return HttpVisionTool(base_url="http://vision", client=client)


async def test_inventory_over_http(vision: HttpVisionTool) -> None:
    out = await vision.build_inventory(
        [ImageRef(uri="1000040420.jpg"), ImageRef(uri="IMG_20260830_132755 (5).jpg")],
        REQS,
    )
    assert [h.id for h in out[0].hits] == [h.id for h in out[1].hits] == ["R-04"]
    assert out[0].hits[0].constraint_ok is True
    assert out[1].hits[0].constraint_ok is False


async def test_whole_submission_in_one_call(vision: HttpVisionTool) -> None:
    """One round trip per job, not per image — 17 calls would blow the latency budget."""
    from pathlib import Path

    # One net-new input folder: images alongside the client's .txt files, which is how
    # a real submission arrives. Only the images go to the vision service.
    folder = Path("fixtures/fleet-vehicle-return/input/netnew/WN-7020U")
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".jpg")
    out = await vision.build_inventory([ImageRef(uri=p.name) for p in images], REQS)
    assert len(out) == len(images) == 17
    assert sum(1 for a in out if a.is_known) == 17


async def test_unreachable_service_raises_vision_unavailable() -> None:
    """Infrastructure failure must not be mistaken for a finding about a photo."""
    tool = HttpVisionTool(base_url="http://127.0.0.1:1", timeout=0.2)
    with pytest.raises(VisionUnavailable):
        await tool.build_inventory([ImageRef(uri="1000040420.jpg")], REQS)
