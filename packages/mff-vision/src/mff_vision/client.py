"""HTTP client for the vision service.

The editor depends on `VisionTool`, never on this class directly, so swapping the
placeholder service for the real one is a wiring change and nothing else.
"""

from __future__ import annotations

import httpx

from .models import ImageAnalysis, ImageRef, RequirementSpec, VisionUnavailable

__all__ = ["HttpVisionTool"]


class HttpVisionTool:
    """Talks to a service implementing the vision API."""

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 300.0,
    ) -> None:
        # A whole job's images in one call, so the timeout is generous by design.
        self._base = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout

    async def build_inventory(
        self,
        images: list[ImageRef],
        requirements: list[RequirementSpec],
    ) -> list[ImageAnalysis]:
        payload = {
            "images": [i.model_dump() for i in images],
            "requirements": [r.model_dump() for r in requirements],
        }
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            r = await client.post(f"{self._base}/v1/inventory", json=payload)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as exc:
            # Unreachable is not the same as unidentifiable: the caller must be able to
            # retry this, and must not record it as a finding about the photographs.
            raise VisionUnavailable(f"vision service {self._base}: {exc}") from exc
        finally:
            if self._client is None:
                await client.aclose()

        results = [ImageAnalysis.model_validate(d) for d in data["images"]]
        if len(results) != len(images):
            raise VisionUnavailable(
                f"vision service returned {len(results)} analyses for {len(images)} "
                "images; the result must be index-aligned with the request"
            )
        return results
