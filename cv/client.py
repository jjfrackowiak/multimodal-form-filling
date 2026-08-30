"""HTTP client the AI editor uses to call the Cloud Run CV tool.

Images stay in GCS. This client sends JSON (`images` + `requirements`).
On Cloud Run (`*.run.app`) it attaches an identity token unless
`authenticated=False`.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from cv.schema import ImageRef, InventoryRequest, InventoryResponse, Requirement


class CvError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"cv HTTP {status}: {body}")
        self.status = status
        self.body = body


def _id_token(audience: str) -> str:
    import google.auth.transport.requests
    import google.oauth2.id_token

    req = google.auth.transport.requests.Request()
    return google.oauth2.id_token.fetch_id_token(req, audience)


class CvClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 300,
        authenticated: bool | None = None,
    ):
        url = (base_url or os.environ.get("CV_URL") or "").rstrip("/")
        if not url:
            raise ValueError("CV_URL is not set")
        self.base_url = url
        self.timeout = timeout
        if authenticated is None:
            authenticated = url.startswith("https://") and "run.app" in url
        self.authenticated = authenticated

    def health(self) -> dict:
        return json.loads(self._request("GET", "/health"))

    def inventory(
        self,
        requirements: list[Requirement] | list[dict],
        *,
        images: list[str] | list[ImageRef] | None = None,
        image_prefix: str | None = None,
        manifest: str | None = None,
    ) -> InventoryResponse:
        refs: list[ImageRef] = []
        for item in images or []:
            refs.append(item if isinstance(item, ImageRef) else ImageRef(uri=item))
        reqs = [
            r if isinstance(r, Requirement) else Requirement.model_validate(r)
            for r in requirements
        ]
        body = InventoryRequest(
            images=refs,
            requirements=reqs,
            image_prefix=image_prefix,
            manifest=manifest,
        )
        raw = self._request(
            "POST",
            "/v1/inventory",
            body.model_dump(mode="json", exclude_none=True),
        )
        return InventoryResponse.model_validate_json(raw)

    def _request(self, method: str, path: str, payload: dict | None = None) -> bytes:
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        if self.authenticated:
            headers["Authorization"] = f"Bearer {_id_token(self.base_url)}"
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            raise CvError(e.code, e.read().decode("utf-8", errors="replace")) from e
