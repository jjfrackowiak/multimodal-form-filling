"""HTTP client for the editor's manifest parser (`POST /manifest:parse`)."""

from __future__ import annotations

import httpx

from mff_contracts import Requirement

__all__ = ["EditorClient"]


def _id_token(audience: str) -> str:
    import google.auth.transport.requests
    import google.oauth2.id_token

    req = google.auth.transport.requests.Request()
    token: str = google.oauth2.id_token.fetch_id_token(req, audience)  # type: ignore[no-untyped-call]
    return token


class EditorClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 120.0,
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

    async def parse_manifest(self, raw: str) -> list[Requirement]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base}/manifest:parse",
                json={"raw": raw},
                headers=self._headers(),
            )
            response.raise_for_status()
        body = response.json()
        return [Requirement.model_validate(row) for row in body["requirements"]]
