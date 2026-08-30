"""HTTP client for the vision service.

The editor depends on `VisionTool`, never on this class directly, so swapping the
placeholder service for the real one is a wiring change and nothing else.
"""

from __future__ import annotations

import httpx

from .models import BoundingBox, ImageAnalysis, ImageRef, VisionUnavailable

__all__ = ["HttpVisionTool"]


class HttpVisionTool:
    """Talks to a service implementing the vision API."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None,
                 timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout

    async def _post(self, path: str, payload: dict) -> dict:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            r = await client.post(f"{self._base}{path}", json=payload)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            # Unreachable is not the same as unidentifiable: the caller must be
            # able to retry this, and must not record it as a finding about the
            # client's photographs.
            raise VisionUnavailable(f"vision service {self._base}: {exc}") from exc
        finally:
            if self._client is None:
                await client.aclose()

    async def describe(self, ref: ImageRef) -> ImageAnalysis:
        data = await self._post("/v1/describe", {"ref": ref.model_dump()})
        return ImageAnalysis.model_validate(data)

    async def describe_many(self, refs: list[ImageRef]) -> list[ImageAnalysis]:
        data = await self._post(
            "/v1/describe:batch", {"refs": [r.model_dump() for r in refs]}
        )
        return [ImageAnalysis.model_validate(d) for d in data["results"]]

    async def crop(self, ref: ImageRef, box: BoundingBox) -> ImageRef:
        data = await self._post(
            "/v1/crop", {"ref": ref.model_dump(), "box": box.model_dump()}
        )
        return ImageRef.model_validate(data)
