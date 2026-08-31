"""HttpVisionTool attaches an identity token on Cloud Run URLs."""

from __future__ import annotations

from unittest.mock import patch

import httpx

import pytest

from mff_contracts import RequirementSpec
from mff_vision import HttpVisionTool, ImageRef, VisionUnavailable


async def test_localhost_is_unauthenticated() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"images": [{"file": "a.jpg", "hits": []}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = HttpVisionTool("http://cv:8080", client=client)
    out = await tool.build_inventory(
        [ImageRef(uri="gs://b/a.jpg")], [RequirementSpec(id="R-01", text="x")]
    )
    assert captured["auth"] is None
    assert out[0].file == "a.jpg"


async def test_run_app_sends_bearer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={"images": [{"file": "a.jpg", "hits": []}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with patch("mff_vision.client._id_token", return_value="tok"):
        tool = HttpVisionTool("https://cv-x.run.app", client=client)
        await tool.build_inventory(
            [ImageRef(uri="gs://b/a.jpg")], [RequirementSpec(id="R-01", text="x")]
        )


async def test_http_error_includes_status_and_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="upstream vertex")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = HttpVisionTool("http://cv:8080", client=client)
    with pytest.raises(VisionUnavailable, match="502") as ei:
        await tool.build_inventory(
            [ImageRef(uri="gs://b/a.jpg")], [RequirementSpec(id="R-01", text="x")]
        )
    assert "upstream vertex" in str(ei.value)
