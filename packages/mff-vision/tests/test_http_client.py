"""HttpVisionTool attaches an identity token on Cloud Run URLs."""

from __future__ import annotations

import json
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


async def test_retries_transient_gateway_failure() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(502, text="temporary upstream failure")
        return httpx.Response(200, json={"images": [{"file": "a.jpg", "hits": []}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = HttpVisionTool("http://cv:8080", client=client, max_retries=1, retry_delay_seconds=0)
    out = await tool.build_inventory(
        [ImageRef(uri="gs://b/a.jpg")], [RequirementSpec(id="R-01", text="x")]
    )

    assert calls == 2
    assert out[0].file == "a.jpg"


async def test_duplicate_uris_are_restored_to_index_aligned_results() -> None:
    """CV de-duplicates URIs, but the editor needs one analysis per input image."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert [image["uri"] for image in json.loads(request.content)["images"]] == [
            "gs://b/a.jpg",
            "gs://b/a.jpg",
        ]
        return httpx.Response(
            200,
            json={"images": [{"file": "a.jpg", "uri": "gs://b/a.jpg", "hits": []}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = HttpVisionTool("http://cv:8080", client=client)
    out = await tool.build_inventory(
        [ImageRef(uri="gs://b/a.jpg"), ImageRef(uri="gs://b/a.jpg")],
        [RequirementSpec(id="R-01", text="x")],
    )

    assert [result.uri for result in out] == ["gs://b/a.jpg", "gs://b/a.jpg"]
