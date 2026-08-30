"""Triggering + idempotency (`DeliveryDispatcher`): the runner's completion callback,
the sweep safety net for a callback lost to a restart, threading against the client's
*original* message rather than our own confirmation, and idempotency on `request_id` —
a callback firing twice, or a callback racing the sweep, must send exactly one email.

Every test here runs against `InMemoryTransport` — no mailbox required (DoD #8).
"""

from __future__ import annotations

from typing import Literal

from email_service.delivery import DeliveryDispatcher, aggregate_result
from email_service.transport import InMemoryTransport
from mff_contracts import BlobRef, JobCursor, JobRecord, RequestRecord, RequestResult
from mff_store import InMemoryBlobStore, InMemoryJobRepository, InMemoryRequestRepository


def _record(
    request_id: str = "req-1",
    status: Literal["running", "delivered", "failed"] = "running",
) -> RequestRecord:
    return RequestRecord(
        request_id=request_id,
        manifest_raw="manifest",
        requirements=[],
        job_ids=["job-1"],
        reply_to="client@example.com",
        original_message_id="<original-client-message@example.com>",
        status=status,
    )


def _result(request_id: str = "req-1") -> RequestResult:
    return RequestResult(
        request_id=request_id, status="done", documents=[], requirements=[], summary={"pass": 1}
    )


def _dispatcher() -> tuple[
    DeliveryDispatcher, InMemoryRequestRepository, InMemoryTransport, InMemoryJobRepository
]:
    requests = InMemoryRequestRepository()
    transport = InMemoryTransport()
    blobs = InMemoryBlobStore()
    jobs = InMemoryJobRepository()
    dispatcher = DeliveryDispatcher(requests=requests, transport=transport, blobs=blobs)
    return dispatcher, requests, transport, jobs


# ---------------------------------------------------------------------------
# Threading — against the ORIGINAL client message, never our own confirmation.
# ---------------------------------------------------------------------------


async def test_threading_targets_the_original_message_not_a_confirmation() -> None:
    dispatcher, requests, _transport, _jobs = _dispatcher()
    record = _record()
    await requests.put(record)

    message = await dispatcher.on_jobs_settled(_result(), record)

    assert message is not None
    assert message.in_reply_to == "<original-client-message@example.com>"
    assert message.references == ["<original-client-message@example.com>"]
    # It would be a bug for this to equal some *other*, confirmation-sent message id —
    # asserting the concrete original id (not merely "is not None") is what would catch
    # a regression that threaded against the confirmation instead.
    assert message.in_reply_to == record.original_message_id


async def test_auto_submitted_is_set_so_other_robots_do_not_reply() -> None:
    dispatcher, requests, _transport, _jobs = _dispatcher()
    record = _record()
    await requests.put(record)
    message = await dispatcher.on_jobs_settled(_result(), record)
    assert message is not None
    assert message.auto_submitted is True


# ---------------------------------------------------------------------------
# Idempotency on request_id.
# ---------------------------------------------------------------------------


async def test_two_callbacks_for_one_request_id_produce_one_send() -> None:
    dispatcher, requests, transport, _jobs = _dispatcher()
    record = _record()
    await requests.put(record)

    first = await dispatcher.on_jobs_settled(_result(), record)
    second = await dispatcher.on_jobs_settled(_result(), record)

    assert first is not None
    assert second is None  # the duplicate is a no-op, not a second message
    assert len(transport.sent) == 1


async def test_delivery_is_recorded_before_the_send_is_acknowledged() -> None:
    dispatcher, requests, transport, _jobs = _dispatcher()
    record = _record()
    await requests.put(record)

    await dispatcher.on_jobs_settled(_result(), record)

    stored = await requests.get(record.request_id)
    assert stored is not None
    assert stored.status == "delivered"
    assert len(transport.sent) == 1


async def test_a_callback_racing_the_sweep_still_sends_once() -> None:
    dispatcher, requests, transport, jobs = _dispatcher()
    record = _record()
    await requests.put(record)
    await jobs.put(
        JobRecord(
            job_id="job-1",
            request_id=record.request_id,
            form_id="form.docx",
            status="done",
            cursor=JobCursor(slice_index=1),
            document=None,
            summary={"pass": 1},
            unverified=[],
        )
    )

    # The callback fires first...
    callback_message = await dispatcher.on_jobs_settled(_result(), record)
    # ...then the sweep independently notices the same (now-delivered) request.
    swept = await dispatcher.sweep([record.request_id], jobs_repo=jobs)

    assert callback_message is not None
    assert swept == []
    assert len(transport.sent) == 1


# ---------------------------------------------------------------------------
# The sweep — the safety net for a callback lost to a restart.
# ---------------------------------------------------------------------------


async def test_sweep_delivers_a_request_whose_callback_never_arrived() -> None:
    dispatcher, requests, _transport, jobs = _dispatcher()
    record = _record()
    await requests.put(record)
    await jobs.put(
        JobRecord(
            job_id="job-1",
            request_id=record.request_id,
            form_id="form.docx",
            status="done",
            cursor=JobCursor(slice_index=1),
            document=None,
            summary={"pass": 3, "fail": 1},
            unverified=["R-02"],
        )
    )

    sent = await dispatcher.sweep([record.request_id], jobs_repo=jobs)

    assert len(sent) == 1
    assert "[R-02]" in sent[0].body
    stored = await requests.get(record.request_id)
    assert stored is not None
    assert stored.status == "delivered"


async def test_sweep_does_not_double_send_a_request_it_already_delivered() -> None:
    dispatcher, requests, transport, jobs = _dispatcher()
    record = _record()
    await requests.put(record)
    await jobs.put(
        JobRecord(
            job_id="job-1",
            request_id=record.request_id,
            form_id="form.docx",
            status="done",
            cursor=JobCursor(slice_index=1),
            document=None,
            summary={"pass": 1},
            unverified=[],
        )
    )

    first_sweep = await dispatcher.sweep([record.request_id], jobs_repo=jobs)
    second_sweep = await dispatcher.sweep([record.request_id], jobs_repo=jobs)

    assert len(first_sweep) == 1
    assert second_sweep == []
    assert len(transport.sent) == 1


async def test_sweep_skips_a_request_still_genuinely_in_flight() -> None:
    dispatcher, requests, transport, jobs = _dispatcher()
    record = _record()
    await requests.put(record)
    await jobs.put(
        JobRecord(
            job_id="job-1",
            request_id=record.request_id,
            form_id="form.docx",
            status="running",
            cursor=JobCursor(slice_index=0),
            document=None,
            summary={},
            unverified=[],
        )
    )

    sent = await dispatcher.sweep([record.request_id], jobs_repo=jobs)

    assert sent == []
    assert transport.sent == []
    stored = await requests.get(record.request_id)
    assert stored is not None
    assert stored.status == "running"


async def test_sweep_ignores_a_request_id_with_no_stored_record() -> None:
    dispatcher, _requests, transport, jobs = _dispatcher()
    sent = await dispatcher.sweep(["never-heard-of-it"], jobs_repo=jobs)
    assert sent == []
    assert transport.sent == []


# ---------------------------------------------------------------------------
# aggregate_result — the sweep's assembly step.
# ---------------------------------------------------------------------------


def test_aggregate_result_collects_documents_unverified_and_failed_forms() -> None:
    record = _record()
    ok_document = BlobRef(
        uri="gs://bucket/jobs/job-1/reviewed/deadbeef",
        content_type="application/octet-stream",
        size_bytes=4,
        sha256="deadbeef",
    )
    records = [
        JobRecord(
            job_id="job-1",
            request_id=record.request_id,
            form_id="ok.docx",
            status="done",
            cursor=JobCursor(slice_index=2),
            document=ok_document,
            summary={"pass": 4, "fail": 0},
            unverified=["R-03"],
        ),
        JobRecord(
            job_id="job-2",
            request_id=record.request_id,
            form_id="broken.docx",
            status="failed",
            cursor=JobCursor(slice_index=1),
            document=None,
            summary={},
            unverified=[],
            failure_detail="editor-service timed out",
        ),
    ]

    result = aggregate_result(record, records)

    assert result.status == "partial"  # a failed job, but the good one still has a doc slot
    assert result.documents == [ok_document]
    assert result.failed_forms == ["broken.docx"]
    assert result.unverified == ["R-03"]
    assert result.summary["pass"] == 4


def test_aggregate_result_is_failed_when_nothing_succeeded() -> None:
    record = _record()
    records = [
        JobRecord(
            job_id="job-1",
            request_id=record.request_id,
            form_id="broken.docx",
            status="failed",
            cursor=JobCursor(slice_index=0),
            document=None,
            summary={},
            unverified=[],
        )
    ]
    result = aggregate_result(record, records)
    assert result.status == "failed"
    assert result.documents == []


def test_aggregate_result_is_done_when_everything_succeeded() -> None:
    record = _record()
    records = [
        JobRecord(
            job_id="job-1",
            request_id=record.request_id,
            form_id="ok.docx",
            status="done",
            cursor=JobCursor(slice_index=2),
            document=None,
            summary={"pass": 10},
            unverified=[],
        )
    ]
    result = aggregate_result(record, records)
    assert result.status == "done"
    assert result.failed_forms == []
