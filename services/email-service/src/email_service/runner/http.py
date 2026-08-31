"""HTTP `SliceRunner` — one POST to the editor's `/slices:run`."""

from __future__ import annotations

import httpx

from mff_contracts import SliceReport, SliceRequest

__all__ = ["HttpSliceRunner"]


def _id_token(audience: str) -> str:
    import google.auth.transport.requests
    import google.oauth2.id_token

    req = google.auth.transport.requests.Request()
    token: str = google.oauth2.id_token.fetch_id_token(req, audience)  # type: ignore[no-untyped-call]
    return token


class HttpSliceRunner:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 600.0,
        authenticated: bool | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        if authenticated is None:
            authenticated = self._base.startswith("https://") and "run.app" in self._base
        self._authenticated = authenticated

    def _headers(self) -> dict[str, str]:
        if not self._authenticated:
            return {}
        return {"Authorization": f"Bearer {_id_token(self._base)}"}

    async def run(self, request: SliceRequest) -> SliceReport:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base}/slices:run",
                json=request.model_dump(mode="json"),
                headers=self._headers(),
            )
            response.raise_for_status()
        return SliceReport.model_validate(response.json())
