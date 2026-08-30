"""Editor calls CV at slice time; cache is per job_id."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from golden import golden_slice_request
from starlette.testclient import TestClient

from editor_service.api.deps import _inventory_by_job, get_slice_runner, inventory_for
from editor_service.main import create_app
from mff_contracts import (
    BlobRef,
    ImageAnalysis,
    JobImage,
    RequirementHit,
    RequirementSpec,
)
from mff_vision import ImageRef, VisionUnavailable


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    _inventory_by_job.clear()
    yield
    _inventory_by_job.clear()


class _FakeVision:
    def __init__(self) -> None:
        self.calls = 0

    async def build_inventory(
        self, images: list[ImageRef], requirements: list[RequirementSpec]
    ) -> list[ImageAnalysis]:
        self.calls += 1
        return [
            ImageAnalysis(
                file=image.name,
                uri=image.uri,
                hits=[RequirementHit(id=requirements[0].id)] if requirements else [],
            )
            for image in images
        ]


def _job_image(uri: str) -> JobImage:
    return JobImage(
        blob=BlobRef(uri=uri, content_type="image/jpeg", size_bytes=1, sha256="a" * 64),
        original_filename=uri.rsplit("/", 1)[-1],
        source="attachment",
    )


async def test_inventory_for_no_images_is_empty() -> None:
    assert await inventory_for(golden_slice_request()) == []


async def test_inventory_for_calls_vision_once_per_job() -> None:
    vision = _FakeVision()
    req = golden_slice_request().model_copy(update={"images": [_job_image("gs://b/jobs/j/a.jpg")]})
    first = await inventory_for(req, vision=vision)
    second = await inventory_for(req, vision=vision)
    assert vision.calls == 1
    assert first == second
    assert first[0].file == "a.jpg"


def test_wired_runner_is_the_default() -> None:
    assert get_slice_runner().__name__ == "run_wired_slice"


def test_missing_cv_url_with_images_is_502(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CV_URL", raising=False)
    monkeypatch.delenv("VISION_SERVICE_URL", raising=False)
    _inventory_by_job.clear()
    body = golden_slice_request().model_copy(update={"images": [_job_image("gs://b/jobs/j/a.jpg")]})
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post("/slices:run", json=body.model_dump(mode="json"))
    assert response.status_code == 502
    assert "CV_URL" in response.json()["detail"]


def test_vision_unavailable_is_not_a_photo_finding() -> None:
    assert issubclass(VisionUnavailable, RuntimeError)
