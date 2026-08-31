"""Email service HTTP + IMAP poller.

CV is not called from here. The editor calls `POST {CV_URL}/v1/inventory` at slice time.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, HTTPException, Request

from email_service.delivery import DeliveryDispatcher
from email_service.intake import RateLimiter
from email_service.orchestrator import OrchestratorDeps
from email_service.poller import Poller, PollerDeps, allowed_from_env, interval_from_env
from email_service.runner import EditorClient, HttpSliceRunner
from email_service.transport import ImapSmtpConfig, ImapSmtpTransport
from mff_contracts import RequestRepository

log = logging.getLogger("email_service")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

__all__ = ["app", "create_app"]


def _build_runtime() -> tuple[OrchestratorDeps, RequestRepository]:
    from mff_store import (
        FirestoreArtifactRepository,
        FirestoreJobRepository,
        FirestoreRequestRepository,
        GcsBlobStore,
        InMemoryArtifactRepository,
        InMemoryBlobStore,
        InMemoryJobRepository,
        InMemoryRequestRepository,
        make_firestore_client,
        make_gcs_client,
    )

    editor_url = os.environ.get("EDITOR_SERVICE_URL", "").rstrip("/")
    if not editor_url:
        raise RuntimeError("EDITOR_SERVICE_URL is not set")
    runner = HttpSliceRunner(editor_url)
    try:
        max_jobs = max(1, int(os.environ.get("MAX_CONCURRENT_JOBS", "1")))
    except ValueError:
        max_jobs = 1

    if os.environ.get("MFF_IN_MEMORY", "").lower() in {"1", "true", "yes"}:
        return (
            OrchestratorDeps(
                artifact_repo=InMemoryArtifactRepository(),
                job_repo=InMemoryJobRepository(),
                blob_store=InMemoryBlobStore(),
                runner=runner,
                max_concurrent_jobs=max_jobs,
            ),
            InMemoryRequestRepository(),
        )

    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("MFF_GCP_PROJECT") or "mff-local"
    )
    bucket = os.environ.get("MFF_GCS_BUCKET") or f"{project}-files"
    fs = make_firestore_client(project)
    gcs = make_gcs_client(project)
    return (
        OrchestratorDeps(
            artifact_repo=FirestoreArtifactRepository(fs),
            job_repo=FirestoreJobRepository(fs),
            blob_store=GcsBlobStore(gcs, bucket=bucket),
            runner=runner,
            max_concurrent_jobs=max_jobs,
        ),
        FirestoreRequestRepository(fs),
    )


def _poller() -> Poller:
    orchestrator, requests = _build_runtime()
    transport = ImapSmtpTransport(ImapSmtpConfig.from_env())
    editor_url = os.environ["EDITOR_SERVICE_URL"].rstrip("/")
    dispatcher = DeliveryDispatcher(
        requests=requests, transport=transport, blobs=orchestrator.blob_store
    )
    max_jobs = int(os.environ.get("MAX_JOBS_PER_SENDER_PER_HOUR", "10"))
    return Poller(
        PollerDeps(
            transport=transport,
            editor=EditorClient(editor_url),
            orchestrator=orchestrator,
            dispatcher=dispatcher,
            rate_limiter=RateLimiter(max_requests=max(1, max_jobs)),
            allowed_senders=allowed_from_env(),
            interval_seconds=interval_from_env(),
        )
    )


def _loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    # Starlette TestClient uses the peer name "testclient", not 127.0.0.1.
    return host in {"127.0.0.1", "::1", "testclient"}


async def _poll_via_http(port: str, interval: float) -> None:
    """Drive process() as an HTTP request so Cloud Run drains it on deploy.

    A background asyncio task is not an in-flight request; SIGTERM kills it and
    SEARCH UNSEEN will not retry a message already past 202. localhost POST keeps
    the work on the request path (service timeout 900s).
    """
    url = f"http://127.0.0.1:{port}/internal/poll"
    timeout = httpx.Timeout(900.0, connect=5.0)
    while True:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url)
                if response.status_code >= 400:
                    log.warning("internal poll HTTP %s", response.status_code)
        except Exception:
            log.exception("internal poll failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if os.environ.get("MFF_DISABLE_POLLER", "").lower() in {"1", "true", "yes"}:
        yield
        return
    if not os.environ.get("EDITOR_SERVICE_URL"):
        log.warning("EDITOR_SERVICE_URL unset; poller not started")
        yield
        return
    app.state.poller = _poller()
    port = os.environ.get("PORT", "8080")
    task = asyncio.create_task(_poll_via_http(port, interval_from_env()), name="imap-poller")
    log.info("poller started")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    app = FastAPI(
        title="Email service",
        version="0.0.0",
        description="Mailbox intake, orchestration, delivery. Editor owns models and CV.",
        lifespan=lifespan,
    )

    @app.get("/health")
    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/poll")
    async def internal_poll(request: Request) -> dict[str, str]:
        if not _loopback(request):
            raise HTTPException(status_code=403, detail="localhost only")
        poller = getattr(request.app.state, "poller", None)
        if poller is None:
            raise HTTPException(status_code=503, detail="poller not started")
        await poller.process()
        return {"status": "ok"}

    return app


app = create_app()
