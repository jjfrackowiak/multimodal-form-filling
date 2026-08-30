"""No Vertex. Hash, checklist, HTTP contract, image-type gate."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from cv.checklist import load_checklist, spans_complete
from cv.images import check_image_name, collapse_duplicates, list_images
from cv.schema import (
    ImageRef,
    Inventory,
    InventoryImage,
    InventoryRequest,
    ParsedChecklist,
    Requirement,
)
from cv.service import _collect_uris, _job_adapter_enabled, health, inventory, process_job

ROOT = Path(__file__).resolve().parents[1]
FLEET_IMAGES = ROOT / "fixtures/fleet-vehicle-return/input/netnew/WN-7020U"


def _req(**kwargs) -> InventoryRequest:
    requirements = kwargs.pop(
        "requirements",
        [Requirement(id="R-01", text="front")],
    )
    images = kwargs.pop("images", [])
    refs = [
        img if isinstance(img, ImageRef) else ImageRef(uri=img) for img in images
    ]
    return InventoryRequest(images=refs, requirements=requirements, **kwargs)


def test_fleet_spans() -> None:
    c = load_checklist(ROOT / "fixtures/fleet-vehicle-return/expected_requirements.yaml")
    assert len(c.requirements) == 10
    assert spans_complete(c)
    assert c.requirements[3].id == "R-04"
    assert c.requirements[3].constraint == "between_front_seats"


def test_fleet_dupes() -> None:
    files = list_images(FLEET_IMAGES)
    unique, pairs = collapse_duplicates(files)
    assert len(files) == 17
    assert len(unique) == 15
    assert len(pairs) == 2


def test_rejects_heic() -> None:
    try:
        check_image_name("photo.HEIC")
    except ValueError as e:
        assert "heic" in str(e).lower()
    else:
        raise AssertionError("expected heic rejection")
    try:
        check_image_name("notes.pdf")
    except ValueError as e:
        assert "not an image" in str(e)
    else:
        raise AssertionError("expected pdf rejection")
    check_image_name("front.jpg")
    check_image_name("side.PNG")
    check_image_name("dash.webp")


def test_health() -> None:
    body = health()
    assert body["ok"] is True
    assert body["service"] == "cv"


def test_inventory_requires_images() -> None:
    try:
        inventory(_req())
    except HTTPException as e:
        assert e.status_code == 400
    else:
        raise AssertionError("expected 400")


def test_inventory_rejects_heic_uri() -> None:
    try:
        inventory(_req(images=["gs://bucket/jobs/a/photo.heic"]))
    except HTTPException as e:
        assert e.status_code == 400
        assert "heic" in str(e.detail).lower()
    else:
        raise AssertionError("expected 400")


def test_inventory_rejects_empty_requirements() -> None:
    try:
        inventory(_req(requirements=[], images=["gs://b/a.jpg"]))
    except HTTPException as e:
        assert e.status_code == 400
    else:
        raise AssertionError("expected 400")


def test_collect_uris_bad_gs() -> None:
    try:
        _collect_uris(_req(images=["https://example/a.jpg"]))
    except HTTPException as e:
        assert e.status_code == 400
    else:
        raise AssertionError("expected 400")


def test_process_disabled() -> None:
    assert not _job_adapter_enabled()
    try:
        process_job({"jobId": "x"})
    except HTTPException as e:
        assert e.status_code == 404
    else:
        raise AssertionError("expected 404")


def test_inventory_http_happy_path() -> None:
    fake_inv = Inventory(
        checklist=ParsedChecklist(requirements=[Requirement(id="R-01", text="front")]),
        images=[
            InventoryImage(
                file="front.jpg",
                uri="gs://bucket/jobs/a/front.jpg",
                note="front",
            )
        ],
    )
    with (
        patch(
            "cv.service.download_uris",
            return_value=[("gs://bucket/jobs/a/front.jpg", Path("/tmp/front.jpg"))],
        ),
        patch("cv.service.build_inventory", return_value=fake_inv) as built,
    ):
        resp = inventory(_req(images=["gs://bucket/jobs/a/front.jpg"]))
    assert resp.images[0].uri == "gs://bucket/jobs/a/front.jpg"
    assert built.call_args.kwargs["source_uris"]["front.jpg"] == "gs://bucket/jobs/a/front.jpg"


if __name__ == "__main__":
    test_fleet_spans()
    test_fleet_dupes()
    test_rejects_heic()
    test_health()
    test_inventory_requires_images()
    test_inventory_rejects_heic_uri()
    test_inventory_rejects_empty_requirements()
    test_collect_uris_bad_gs()
    test_process_disabled()
    test_inventory_http_happy_path()
    print("offline ok")
