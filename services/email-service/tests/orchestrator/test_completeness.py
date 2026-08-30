"""DoD #8 — the completeness check catches a dropped slice.

Cross-slice by construction: a fake runner that silently drops one requirement's
comment (as opposed to marking it `unverified`, which is a legitimate terminal
verdict) leaves the artifact with 9 of 10 requirements covered after both slices have
run. No single slice run could have caught this — it only ever sees six or four
requirements. The orchestrator, seeing all ten after the last slice, must.
"""

from __future__ import annotations

from factories import load_requirements, load_review_comments, make_deps, make_derivative_job
from email_service.orchestrator.completeness import missing_requirement_ids
from email_service.orchestrator.job import run_job
from email_service.runner.fake import FakeSliceRunner


async def test_dropped_requirement_fails_the_job_not_silently_delivered() -> None:
    requirements = load_requirements()
    comments = {rid: c for rid, c in load_review_comments().items() if rid != "R-08"}

    runner = FakeSliceRunner(comments=comments)
    deps = make_deps(runner=runner)
    job = await make_derivative_job(deps.blob_store, requirements=requirements)

    record = await run_job(job, deps)

    assert record.status == "failed"
    assert record.document is None
    assert record.failure_detail is not None
    assert "R-08" in record.failure_detail
    # Both slices still ran to completion — the gap is only visible after the last one.
    assert [call.slice_id for call in runner.calls] == ["slice-01", "slice-02"]


def test_missing_requirement_ids_is_pure_and_order_preserving() -> None:
    requirements = load_requirements()
    comments = load_review_comments()
    del comments["R-03"]
    del comments["R-09"]

    missing = missing_requirement_ids(requirements, list(comments.values()))

    assert missing == ["R-03", "R-09"]


def test_missing_requirement_ids_empty_when_every_requirement_is_covered() -> None:
    requirements = load_requirements()
    comments = load_review_comments()

    assert missing_requirement_ids(requirements, list(comments.values())) == []
