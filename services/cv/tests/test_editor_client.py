"""Editor HttpVisionTool against the real CV FastAPI app (Vertex/GCS mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from cv.schema import (
    Inventory,
    InventoryImage,
    ParsedChecklist,
    Requirement,
    RequirementHit,
)
from cv.service import app
from mff_vision import Constraint, HttpVisionTool, ImageRef, RequirementSpec


@pytest.fixture
def vision() -> HttpVisionTool:
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://cv")
    return HttpVisionTool(base_url="http://cv", client=client)


async def test_editor_client_round_trips_structured_constraint(
    vision: HttpVisionTool,
) -> None:
    """The payload the editor already sends must come back as ImageAnalysis hits."""
    uri = "gs://bucket/jobs/abc/1000040420.jpg"
    fake = Inventory(
        checklist=ParsedChecklist(requirements=[Requirement(id="R-04", text="headliner")]),
        images=[
            InventoryImage(
                file="1000040420.jpg",
                uri=uri,
                hits=[
                    RequirementHit(
                        id="R-04",
                        constraint_ok=True,
                        constraint_evidence="between the front seats",
                    )
                ],
                note="headliner from between the seats",
            )
        ],
    )
    reqs = [
        RequirementSpec(
            id="R-04",
            text="Two photographs of the headliner.",
            constraint=Constraint(
                kind="camera_position",
                value="between_front_seats",
                source_span="Headliner must be taken from between the seats",
                source_line=10,
            ),
        )
    ]
    with (
        patch(
            "cv.service.download_uris",
            return_value=[(uri, Path("/tmp/1000040420.jpg"))],
        ),
        patch("cv.service.build_inventory", return_value=fake) as built,
    ):
        out = await vision.build_inventory([ImageRef(uri=uri)], reqs)

    assert len(out) == 1
    assert out[0].file == "1000040420.jpg"
    assert out[0].uri == uri
    assert [h.id for h in out[0].hits] == ["R-04"]
    assert out[0].hits[0].constraint_ok is True
    assert out[0].is_known is True
    passed = built.call_args.args[1] if built.call_args.args else built.call_args[0][1]
    assert passed.requirements[0].constraint == "between_front_seats"


async def test_editor_client_index_aligns_unknown_photo(
    vision: HttpVisionTool,
) -> None:
    uri = "gs://bucket/jobs/abc/mystery.jpg"
    fake = Inventory(
        checklist=ParsedChecklist(requirements=[Requirement(id="R-01", text="front")]),
        images=[],
    )
    with (
        patch("cv.service.download_uris", return_value=[(uri, Path("/tmp/mystery.jpg"))]),
        patch("cv.service.build_inventory", return_value=fake),
    ):
        out = await vision.build_inventory(
            [ImageRef(uri=uri)],
            [RequirementSpec(id="R-01", text="A photograph of the front of the vehicle.")],
        )
    assert len(out) == 1
    assert out[0].hits == []
    assert out[0].is_known is False
