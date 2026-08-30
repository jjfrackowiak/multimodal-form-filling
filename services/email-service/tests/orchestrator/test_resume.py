"""DoD #3 — resume test: kill after slice 1, restart, assert slice 2 runs and slice 1
does not.

"Restart" here means calling `run_job` again against the same (persistent) repos with
a *new* runner instance — nothing in `run_job` remembers anything in-process between
calls; all resumable state lives in `ArtifactRepository`/`JobRepository`, exactly as
the brief requires ("state outside any run", req 12).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from factories import load_review_comments, make_deps, make_derivative_job

from email_service.orchestrator.job import run_job
from email_service.runner.fake import FakeSliceRunner
from mff_contracts import DerivativeArtifact, SliceReport, SliceRequest


def _crash_on_second_call() -> tuple[list[SliceRequest], Callable[[SliceRequest], SliceReport]]:
    calls: list[SliceRequest] = []
    comments_table = load_review_comments()

    def handler(request: SliceRequest) -> SliceReport:
        calls.append(request)
        if len(calls) >= 2:
            raise RuntimeError("simulated crash mid-slice-2")
        comments = [comments_table[r.id] for r in request.requirements]
        return SliceReport(
            slice_id=request.slice_id, comments=comments, ops=[], unverified=[], attempts_used=1
        )

    return calls, handler


async def test_crash_mid_slice_two_then_resume_runs_only_slice_two() -> None:
    _calls, handler = _crash_on_second_call()
    crashing_runner = FakeSliceRunner(handler=handler)
    deps = make_deps(runner=crashing_runner)
    job = await make_derivative_job(deps.blob_store)

    with pytest.raises(RuntimeError, match="simulated crash"):
        await run_job(job, deps)

    # Slice 1 landed; slice 2's crash left nothing behind (mff_store's atomicity).
    artifact, cursor, version = await deps.artifact_repo.load(job.job_id)
    assert cursor.slice_index == 0
    assert version == 1
    assert isinstance(artifact, DerivativeArtifact)
    assert {c.requirement_id for c in artifact.comments} == {f"R-{i:02d}" for i in range(1, 7)}

    # "Restart": same repos, a fresh runner (a new process, in spirit).
    resumed_runner = FakeSliceRunner(comments=load_review_comments())
    resumed_deps = make_deps(
        runner=resumed_runner,
        artifact_repo=deps.artifact_repo,
        job_repo=deps.job_repo,
        blob_store=deps.blob_store,
    )

    record = await run_job(job, resumed_deps)

    assert record.status == "done"
    # Only slice 2 was dispatched on the resumed run — slice 1 was not replayed.
    assert [call.slice_id for call in resumed_runner.calls] == ["slice-02"]

    final_artifact, final_cursor, final_version = await deps.artifact_repo.load(job.job_id)
    assert final_cursor.slice_index == 1
    assert final_version == 2
    assert isinstance(final_artifact, DerivativeArtifact)
    assert {c.requirement_id for c in final_artifact.comments} == {
        f"R-{i:02d}" for i in range(1, 11)
    }
