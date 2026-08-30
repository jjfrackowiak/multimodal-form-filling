"""DoD #6 — the delivery barrier: 2 done + 1 failed -> `RequestResult.status ==
"partial"`, `failed_forms` names the third, `documents` has 2 entries.

The failing job here fails via the completeness check (a dropped requirement's
comment never lands), not a raised exception — proving a job that *settles* as
`"failed"` still respects the barrier the same way a crashed one would, and never
becomes part of `documents`.
"""

from __future__ import annotations

from mff_contracts import RequestRecord

from factories import (
    RoutingSliceRunner,
    load_requirements,
    load_review_comments,
    make_deps,
    make_derivative_job,
)
from email_service.orchestrator.request import run_request
from email_service.runner.fake import FakeSliceRunner


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
