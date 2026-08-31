"""DoD #6 — the delivery barrier: 2 done + 1 failed -> `RequestResult.status ==
"partial"`, `failed_forms` names the third, `documents` has 2 entries.

The failing job here fails via the completeness check (a dropped requirement's
comment never lands), not a raised exception — proving a job that *settles* as
`"failed"` still respects the barrier the same way a crashed one would, and never
becomes part of `documents`.
"""

from __future__ import annotations

from typing import Never

from factories import (
    RoutingSliceRunner,
    load_requirements,
    load_review_comments,
    make_deps,
    make_derivative_job,
)

from email_service.orchestrator.request import run_request
from email_service.runner.fake import FakeSliceRunner
from mff_contracts import RequestRecord, SliceRequest


async def test_two_done_one_failed_settles_partial() -> None:
    requirements = load_requirements()
    full_comments = load_review_comments()
    dropped_comments = {rid: c for rid, c in full_comments.items() if rid != "R-05"}

    router = RoutingSliceRunner()
    deps = make_deps(runner=router)

    job_a = await make_derivative_job(
        deps.blob_store, job_id="job-a", form_id="form-a.docx", requirements=requirements
    )
    job_b = await make_derivative_job(
        deps.blob_store, job_id="job-b", form_id="form-b.docx", requirements=requirements
    )
    job_c = await make_derivative_job(
        deps.blob_store, job_id="job-c", form_id="form-c.docx", requirements=requirements
    )
    router.by_job_id = {
        job_a.job_id: FakeSliceRunner(comments=full_comments),
        job_b.job_id: FakeSliceRunner(comments=full_comments),
        job_c.job_id: FakeSliceRunner(comments=dropped_comments),  # R-05 never gets a comment
    }

    record = RequestRecord(
        request_id="req-barrier",
        manifest_raw="irrelevant to this test",
        requirements=requirements,
        job_ids=[job_a.job_id, job_b.job_id, job_c.job_id],
        reply_to="client@example.test",
        original_message_id="<abc@example.test>",
        status="running",
    )

    result = await run_request(record, [job_a, job_b, job_c], deps)

    assert result.status == "partial"
    assert result.failed_forms == ["form-c.docx"]
    assert len(result.documents) == 2

    job_c_record = await deps.job_repo.get(job_c.job_id)
    assert job_c_record is not None
    assert job_c_record.status == "failed"
    assert job_c_record.failure_detail is not None
    assert "R-05" in job_c_record.failure_detail


async def test_every_job_failed_settles_failed_not_partial() -> None:
    requirements = load_requirements()
    dropped_comments = {rid: c for rid, c in load_review_comments().items() if rid != "R-05"}

    router = RoutingSliceRunner()
    deps = make_deps(runner=router)
    job_a = await make_derivative_job(
        deps.blob_store, job_id="job-a", form_id="form-a.docx", requirements=requirements
    )
    job_b = await make_derivative_job(
        deps.blob_store, job_id="job-b", form_id="form-b.docx", requirements=requirements
    )
    router.by_job_id = {
        job_a.job_id: FakeSliceRunner(comments=dropped_comments),
        job_b.job_id: FakeSliceRunner(comments=dropped_comments),
    }

    record = RequestRecord(
        request_id="req-all-failed",
        manifest_raw="irrelevant to this test",
        requirements=requirements,
        job_ids=[job_a.job_id, job_b.job_id],
        reply_to="client@example.test",
        original_message_id="<abc@example.test>",
        status="running",
    )

    result = await run_request(record, [job_a, job_b], deps)

    assert result.status == "failed"
    assert sorted(result.failed_forms) == ["form-a.docx", "form-b.docx"]
    assert result.documents == []


class _ExplodingRunner:
    async def run(self, request: SliceRequest) -> Never:
        del request
        raise RuntimeError("Server error '502 Bad Gateway' for url 'https://editor/slices:run'")


async def test_runner_exception_on_one_job_still_delivers_the_other() -> None:
    requirements = load_requirements()
    full_comments = load_review_comments()

    router = RoutingSliceRunner()
    deps = make_deps(runner=router)

    job_ok = await make_derivative_job(
        deps.blob_store, job_id="job-ok", form_id="form_supplied.docx", requirements=requirements
    )
    job_boom = await make_derivative_job(
        deps.blob_store, job_id="job-boom", form_id="WN-7020U", requirements=requirements
    )
    router.by_job_id = {
        job_ok.job_id: FakeSliceRunner(comments=full_comments),
        job_boom.job_id: _ExplodingRunner(),
    }

    record = RequestRecord(
        request_id="req-explode",
        manifest_raw="irrelevant",
        requirements=requirements,
        job_ids=[job_ok.job_id, job_boom.job_id],
        reply_to="client@example.test",
        original_message_id="<abc@example.test>",
        status="running",
    )

    result = await run_request(record, [job_ok, job_boom], deps)

    assert result.status == "partial"
    assert result.failed_forms == ["WN-7020U"]
    assert len(result.documents) == 1
    boom = await deps.job_repo.get(job_boom.job_id)
    assert boom is not None
    assert boom.status == "failed"
    assert boom.failure_detail is not None
    assert "502" in boom.failure_detail
