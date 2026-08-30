"""HTTP client for the CV tool (`POST /v1/inventory`).

The editor depends on `VisionTool`, never on this class directly. Cloud Run URLs
(`*.run.app`) get an identity token; compose / localhost do not.
"""

from __future__ import annotations

import httpx

from .models import ImageAnalysis, ImageRef, RequirementSpec, VisionUnavailable

__all__ = ["HttpVisionTool"]


def _id_token(audience: str) -> str:
    import google.auth.transport.requests
    import google.oauth2.id_token

    req = google.auth.transport.requests.Request()
    token: str = google.oauth2.id_token.fetch_id_token(req, audience)  # type: ignore[no-untyped-call]
    return token


class HttpVisionTool:
    """Talks to CV (`POST /v1/inventory`)."""

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 300.0,
        authenticated: bool | None = None,
    ) -> None:
        # A whole job's images in one call, so the timeout is generous by design.
        self._base = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout
        if authenticated is None:
            authenticated = self._base.startswith("https://") and "run.app" in self._base
        self._authenticated = authenticated

    def _headers(self) -> dict[str, str]:
        if not self._authenticated:
            return {}
        return {"Authorization": f"Bearer {_id_token(self._base)}"}

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
            r = await client.post(
                f"{self._base}/v1/inventory",
                json=payload,
                headers=self._headers(),
            )
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
