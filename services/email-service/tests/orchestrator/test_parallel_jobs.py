"""DoD #5 — a mixed request of 3 derivative + 4 net-new jobs: concurrency is bounded,
each job gets its own artifact, and derivative jobs produce `DerivativeArtifact` while
net-new jobs produce `NetNewArtifact`. `mode` is per job — never assume a request is
homogeneous.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from factories import load_requirements, make_deps, make_derivative_job, make_netnew_job

from email_service.orchestrator.request import run_request
from email_service.runner.fake import FakeSliceRunner
from mff_contracts import (
    Anchor,
    DerivativeArtifact,
    NetNewArtifact,
    RequestRecord,
    ReviewComment,
    SliceReport,
    SliceRequest,
)


def _tracking_handler(
    max_concurrent: list[int], current: list[int]
) -> Callable[[SliceRequest], Awaitable[SliceReport]]:
    async def handler(request: SliceRequest) -> SliceReport:
        current[0] += 1
        max_concurrent[0] = max(max_concurrent[0], current[0])
        try:
            await asyncio.sleep(0.02)  # force overlap so bounding is actually exercised
            comments = [
                ReviewComment(
                    requirement_id=r.id,
                    anchor=Anchor(kind="document"),
                    verdict="pass",
                    justification="ok for this test",
                )
                for r in request.requirements
            ]
            return SliceReport(
                slice_id=request.slice_id, comments=comments, ops=[], unverified=[], attempts_used=1
            )
        finally:
            current[0] -= 1

    return handler


async def test_mixed_request_bounds_concurrency_and_types_artifacts_correctly() -> None:
    requirements = load_requirements()[:1]  # one requirement per job — this test is about shape
    max_concurrent = [0]
    current = [0]
    runner = FakeSliceRunner(handler=_tracking_handler(max_concurrent, current))

    deps = make_deps(runner=runner, max_concurrent_jobs=2)
    derivative_jobs = [
        await make_derivative_job(
            deps.blob_store,
            job_id=f"job-d-{i}",
            form_id=f"form-d-{i}.docx",
            requirements=requirements,
        )
        for i in range(3)
    ]
    netnew_jobs = [
        make_netnew_job(job_id=f"job-n-{i}", form_id=f"form-n-{i}", requirements=requirements)
        for i in range(4)
    ]
    jobs = [*derivative_jobs, *netnew_jobs]

    record = RequestRecord(
        request_id="req-mixed",
        manifest_raw="irrelevant to this test",
        requirements=requirements,
        job_ids=[j.job_id for j in jobs],
        reply_to="client@example.test",
        original_message_id="<abc@example.test>",
        status="running",
    )

    result = await run_request(record, jobs, deps)

    assert result.status == "done"
    assert len(result.documents) == 7
    assert max_concurrent[0] <= 2  # bounded by max_concurrent_jobs
    assert max_concurrent[0] > 1  # and genuinely overlapped, not serialised

    for job in derivative_jobs:
        artifact, _cursor, _version = await deps.artifact_repo.load(job.job_id)
        assert isinstance(artifact, DerivativeArtifact)
        assert artifact.form_id == job.job_id

    for job in netnew_jobs:
        artifact, _cursor, _version = await deps.artifact_repo.load(job.job_id)
        assert isinstance(artifact, NetNewArtifact)
        assert artifact.form_id == job.job_id
