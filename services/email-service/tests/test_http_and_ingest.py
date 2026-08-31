"""HTTP editor client, ingest lift, healthz, poller."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest
from starlette.testclient import TestClient

from email_service.delivery import DeliveryDispatcher
from email_service.intake import ParsedForm, ParsedJob, ParsedRequest, RateLimiter
from email_service.orchestrator import OrchestratorDeps, jobs_from_parsed
from email_service.poller import Poller, PollerDeps, interval_from_env
from email_service.runner import EditorClient, FakeSliceRunner, HttpSliceRunner
from email_service.transport import InMemoryTransport
from email_service.transport.messages import InboundMessage
from mff_contracts import Anchor, Mode, Requirement, ReviewComment
from mff_store import InMemoryArtifactRepository, InMemoryBlobStore, InMemoryJobRepository
from mff_store.memory import InMemoryRequestRepository


def _requirement() -> Requirement:
    return Requirement(
        id="R-01",
        ordinal=0,
        text="A photograph of the engine bay.",
        source_span="Under the bonnet",
        source_line=2,
    )


def test_interval_from_env_defaults_and_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POLL_INTERVAL_SECONDS", raising=False)
    assert interval_from_env() == 15.0
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "1")
    assert interval_from_env() == 5.0
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "nope")
    assert interval_from_env() == 15.0


def test_healthz_does_not_start_the_poller(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MFF_DISABLE_POLLER", "1")
    monkeypatch.delenv("EDITOR_SERVICE_URL", raising=False)
    from email_service.main import create_app

    client = TestClient(create_app())
    assert client.get("/healthz").json() == {"status": "ok"}


async def test_jobs_from_parsed_puts_docx_and_images() -> None:
    blobs = InMemoryBlobStore()
    parsed = ParsedRequest(
        message_id="<m@x>",
        sender="a@b.test",
        subject="s",
        manifest_raw="Under the bonnet",
        jobs=[
            ParsedJob(
                mode=Mode.DERIVATIVE,
                form_id="form.docx",
                form=ParsedForm(filename="form.docx", data=b"PK\x03\x04docx"),
            )
        ],
    )
    jobs = await jobs_from_parsed(
        parsed, request_id="req-1", requirements=[_requirement()], blobs=blobs
    )
    assert len(jobs) == 1
    assert jobs[0].mode is Mode.DERIVATIVE
    assert jobs[0].form is not None
    assert jobs[0].images == []
    assert await blobs.get(jobs[0].form) == b"PK\x03\x04docx"


async def test_jobs_from_parsed_extracts_embedded_photos_from_derivative_docx() -> None:
    from pathlib import Path

    docx = (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "fleet-vehicle-return"
        / "input"
        / "derivative"
        / "form_supplied.docx"
    )
    blobs = InMemoryBlobStore()
    parsed = ParsedRequest(
        message_id="<m@x>",
        sender="a@b.test",
        subject="s",
        manifest_raw="Under the bonnet",
        jobs=[
            ParsedJob(
                mode=Mode.DERIVATIVE,
                form_id="form_supplied.docx",
                form=ParsedForm(filename="form_supplied.docx", data=docx.read_bytes()),
            )
        ],
    )
    jobs = await jobs_from_parsed(
        parsed, request_id="req-1", requirements=[_requirement()], blobs=blobs
    )
    assert len(jobs[0].images) == 15
    assert {image.source for image in jobs[0].images} == {"embedded"}
    assert all(image.blob.uri for image in jobs[0].images)


async def test_http_slice_runner_posts_json() -> None:
    from mff_contracts import BlobRef, DerivativeArtifact, SliceRequest

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/slices:run"
        return httpx.Response(
            200,
            json={
                "slice_id": "slice-01",
                "comments": [],
                "ops": [],
                "unverified": [],
                "attempts_used": 1,
            },
        )

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    runner = HttpSliceRunner("http://editor", authenticated=False)
    req = SliceRequest(
        job_id="j-1",
        slice_id="slice-01",
        mode=Mode.DERIVATIVE,
        requirements=[_requirement()],
        artifact=DerivativeArtifact(
            job_id="j-1",
            form_id="j-1",
            source=BlobRef(uri="gs://b/s", content_type="a/b", size_bytes=1, sha256="a" * 64),
        ),
    )
    with patch(
        "email_service.runner.http.httpx.AsyncClient",
        lambda *args, **kwargs: orig(transport=transport),
    ):
        report = await runner.run(req)
    assert report.slice_id == "slice-01"
    assert report.attempts_used == 1


async def test_editor_client_parses_manifest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/manifest:parse"
        return httpx.Response(200, json={"requirements": [_requirement().model_dump(mode="json")]})

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient
    client = EditorClient("http://editor", authenticated=False)
    with patch(
        "email_service.runner.editor.httpx.AsyncClient",
        lambda *args, **kwargs: orig(transport=transport),
    ):
        reqs = await client.parse_manifest("Under the bonnet")
    assert reqs[0].id == "R-01"


class _Editor:
    async def parse_manifest(self, raw: str) -> list[Requirement]:
        del raw
        return [_requirement()]


async def test_poller_rejects_unknown_sender() -> None:
    transport = InMemoryTransport()
    transport.deliver(
        InboundMessage(
            message_id="<1@x>",
            sender="stranger@x.test",
            subject="hi",
            body="Under the bonnet",
            received_at=datetime.now(UTC),
        )
    )
    blobs = InMemoryBlobStore()
    requests = InMemoryRequestRepository()
    jobs = InMemoryJobRepository()
    artifacts = InMemoryArtifactRepository()
    runner = FakeSliceRunner(
        comments={
            "R-01": ReviewComment(
                requirement_id="R-01",
                anchor=Anchor(kind="document"),
                verdict="pass",
                justification="ok",
            )
        }
    )
    poller = Poller(
        PollerDeps(
            transport=transport,
            editor=_Editor(),
            orchestrator=OrchestratorDeps(
                artifact_repo=artifacts,
                job_repo=jobs,
                blob_store=blobs,
                runner=runner,
            ),
            dispatcher=DeliveryDispatcher(requests=requests, transport=transport, blobs=blobs),
            rate_limiter=RateLimiter(),
            allowed_senders=frozenset({"ok@x.test"}),
            interval_seconds=15,
        )
    )
    await poller.process()
    assert transport.sent
    assert "sender_not_allowed" in transport.sent[0].body
    assert "ALLOWED_SENDERS" in transport.sent[0].body


def test_loopback_hosts() -> None:
    from starlette.requests import Request

    from email_service.main import _loopback

    def make(host: str) -> Request:
        return Request(
            {
                "type": "http",
                "asgi": {"spec_version": "2.3", "version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/internal/poll",
                "raw_path": b"/internal/poll",
                "query_string": b"",
                "headers": [],
                "client": (host, 1),
                "server": ("127.0.0.1", 80),
            }
        )

    assert _loopback(make("127.0.0.1"))
    assert _loopback(make("::1"))
    assert _loopback(make("testclient"))
    assert not _loopback(make("8.8.8.8"))


def test_internal_poll_runs_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MFF_DISABLE_POLLER", "1")
    from email_service.main import create_app

    calls: list[int] = []

    class _FakePoller:
        async def process(self) -> None:
            calls.append(1)

    with TestClient(create_app()) as client:
        client.app.state.poller = _FakePoller()
        response = client.post("/internal/poll")
    assert response.status_code == 200
    assert calls == [1]


def test_internal_poll_without_poller_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MFF_DISABLE_POLLER", "1")
    from email_service.main import create_app

    with TestClient(create_app()) as client:
        response = client.post("/internal/poll")
    assert response.status_code == 503
