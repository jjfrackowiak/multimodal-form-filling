"""IMAP poll loop: ingest → editor (manifest) → orchestrator → delivery.

CV is not called here. The editor calls CV at slice time.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Protocol

from email_service.delivery import DeliveryDispatcher
from email_service.intake import (
    RateLimiter,
    allowed_senders_from_env,
    parse_inbound,
    validate_intake,
)
from email_service.orchestrator import OrchestratorDeps, jobs_from_parsed, run_request
from email_service.replies import render_confirmation, render_rejection
from email_service.transport import InboundMessage, MailTransport, should_auto_reply
from mff_contracts import RequestAccepted, RequestRecord, Requirement
from mff_store.errors import NotFoundError

log = logging.getLogger("email_service.poller")

__all__ = ["ManifestParser", "Poller", "PollerDeps"]


class ManifestParser(Protocol):
    async def parse_manifest(self, raw: str) -> list[Requirement]: ...


@dataclass(frozen=True, slots=True)
class PollerDeps:
    transport: MailTransport
    editor: ManifestParser
    orchestrator: OrchestratorDeps
    dispatcher: DeliveryDispatcher
    rate_limiter: RateLimiter
    allowed_senders: frozenset[str]
    interval_seconds: float = 15.0


class Poller:
    def __init__(self, deps: PollerDeps) -> None:
        self._deps = deps
        self._busy = asyncio.Lock()

    async def process(self) -> None:
        async with self._busy:
            unseen = await self._deps.transport.fetch_unseen()
            for inbound in unseen:
                try:
                    await self._handle(inbound)
                except Exception:
                    log.exception("failed on message %s", inbound.message_id)
                await self._deps.transport.mark_seen(inbound.message_id)

    async def run_forever(self) -> None:
        while True:
            try:
                await self.process()
            except Exception:
                log.exception("poll failed")
            await asyncio.sleep(self._deps.interval_seconds)

    async def _handle(self, inbound: InboundMessage) -> None:
        if not should_auto_reply(inbound):
            return
        parsed = parse_inbound(inbound)
        verdict = validate_intake(
            parsed,
            allowed_senders=self._deps.allowed_senders,
            rate_limiter=self._deps.rate_limiter,
        )
        if not verdict.valid:
            await self._deps.transport.send(render_rejection(verdict, parsed))
            return

        requirements = await self._deps.editor.parse_manifest(parsed.manifest_raw)
        request_id = uuid.uuid4().hex[:12]
        accepted = RequestAccepted(request_id=request_id, requirements=requirements)
        if should_auto_reply(inbound):
            await self._deps.transport.send(render_confirmation(accepted, parsed))

        jobs = await jobs_from_parsed(
            parsed,
            request_id=request_id,
            requirements=requirements,
            blobs=self._deps.orchestrator.blob_store,
        )
        record = RequestRecord(
            request_id=request_id,
            manifest_raw=parsed.manifest_raw,
            requirements=requirements,
            job_ids=[job.job_id for job in jobs],
            reply_to=parsed.sender,
            original_message_id=parsed.message_id,
            status="running",
        )
        await self._deps.dispatcher.requests.put(record)
        result = await run_request(record, jobs, self._deps.orchestrator)
        comments = []
        job_records = []
        for job in jobs:
            stored = await self._deps.orchestrator.job_repo.get(job.job_id)
            if stored is not None:
                job_records.append(stored)
            try:
                artifact, _, _ = await self._deps.orchestrator.artifact_repo.load(job.job_id)
            except NotFoundError:
                continue
            comments.extend(artifact.comments)
        await self._deps.dispatcher.on_jobs_settled(
            result, record, comments=comments, jobs=job_records
        )


def interval_from_env() -> float:
    raw = os.environ.get("POLL_INTERVAL_SECONDS", "15").strip()
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 15.0


def allowed_from_env() -> frozenset[str]:
    return allowed_senders_from_env()
