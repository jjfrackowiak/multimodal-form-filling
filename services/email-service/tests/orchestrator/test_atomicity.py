"""DoD #4 — atomicity test: crash between the artifact write and the cursor write
leaves neither.

Exercises `mff_store`'s injected fault (`InMemoryArtifactRepository.fail_before_cursor_
write`) *through* `run_job`, proving the orchestrator does not paper over — or half
apply — a broken `save`: the exception propagates, nothing is left committed, and a
retried `run_job` call runs cleanly from scratch.
"""

from __future__ import annotations

import pytest
from factories import load_review_comments, make_deps, make_derivative_job

from email_service.orchestrator.job import run_job
from email_service.runner.fake import FakeSliceRunner
from mff_contracts import DerivativeArtifact
from mff_store.errors import NotFoundError


async def test_crash_between_artifact_and_cursor_write_leaves_neither() -> None:
    runner = FakeSliceRunner(comments=load_review_comments())
    deps = make_deps(runner=runner)
    job = await make_derivative_job(deps.blob_store)
    deps.artifact_repo.fail_before_cursor_write = True  # type: ignore[attr-defined]

    with pytest.raises(Exception, match="simulated crash"):
        await run_job(job, deps)

    with pytest.raises(NotFoundError):
        await deps.artifact_repo.load(job.job_id)

    # Clean enough for a plain retry to succeed from slice 0.
    deps.artifact_repo.fail_before_cursor_write = False  # type: ignore[attr-defined]
    fresh_runner = FakeSliceRunner(comments=load_review_comments())
    fresh_deps = make_deps(
        runner=fresh_runner,
        artifact_repo=deps.artifact_repo,
        job_repo=deps.job_repo,
        blob_store=deps.blob_store,
    )

    record = await run_job(job, fresh_deps)

    assert record.status == "done"
    assert [call.slice_id for call in fresh_runner.calls] == ["slice-01", "slice-02"]
    artifact, cursor, version = await deps.artifact_repo.load(job.job_id)
    assert isinstance(artifact, DerivativeArtifact)
    assert cursor.slice_index == 1
    assert version == 2
