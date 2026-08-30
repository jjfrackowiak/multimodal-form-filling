"""Email service HTTP + IMAP poller.

CV is not called from here. The editor calls `POST {CV_URL}/v1/inventory` at slice time.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

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

    if os.environ.get("MFF_IN_MEMORY", "").lower() in {"1", "true", "yes"}:
        return (
            OrchestratorDeps(
                artifact_repo=InMemoryArtifactRepository(),
                job_repo=InMemoryJobRepository(),
                blob_store=InMemoryBlobStore(),
                runner=runner,
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


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if os.environ.get("MFF_DISABLE_POLLER", "").lower() in {"1", "true", "yes"}:
        yield
        return
    if not os.environ.get("EDITOR_SERVICE_URL"):
        log.warning("EDITOR_SERVICE_URL unset; poller not started")
        yield
        return
    poller = _poller()
    task = asyncio.create_task(poller.run_forever(), name="imap-poller")
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

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
