"""Round-trip the real client against the real service over real HTTP.

Proves the two halves agree. Without this, the client and the service can drift
apart and nothing notices until Michal's service arrives and the payload shapes
turn out never to have matched.
"""

from __future__ import annotations

import httpx
import pytest
from mff_vision import BoundingBox, HttpVisionTool, ImageRef, VisionUnavailable

from vision_stub.main import create_app


@pytest.fixture
def vision() -> HttpVisionTool:
    transport = httpx.ASGITransport(app=create_app())
    client = httpx.AsyncClient(transport=transport, base_url="http://vision")
    return HttpVisionTool(base_url="http://vision", client=client)


async def test_describe_over_http(vision: HttpVisionTool) -> None:
    out = await vision.describe(ImageRef(uri="1000040420.jpg"))
    assert out.depicts == "headliner"
    assert out.shot_from == "between_front_seats"


async def test_batch_over_http(vision: HttpVisionTool) -> None:
    refs = [ImageRef(uri="1000040420.jpg"), ImageRef(uri="IMG_20260830_132755 (5).jpg")]
    out = await vision.describe_many(refs)
    assert [a.shot_from for a in out] == ["between_front_seats", "beside_seat"]


async def test_crop_over_http(vision: HttpVisionTool) -> None:
    out = await vision.crop(
        ImageRef(uri="1000040420.jpg"),
        BoundingBox(left=0.0, top=0.0, right=0.5, bottom=0.5),
    )
    assert "crop=" in out.uri


async def test_unreachable_service_raises_vision_unavailable() -> None:
    """Infrastructure failure must not be mistaken for a finding about a photo."""
    tool = HttpVisionTool(base_url="http://127.0.0.1:1", timeout=0.2)
    with pytest.raises(VisionUnavailable):
        await tool.describe(ImageRef(uri="1000040420.jpg"))
