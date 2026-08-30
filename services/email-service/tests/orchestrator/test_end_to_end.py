"""DoD #2: a full derivative job walked end-to-end with a fake runner on the fleet
fixture — 2 slices, 10 requirements, correct commit order — no editor service, no
HTTP, no model.
"""

from __future__ import annotations

from mff_contracts import DerivativeArtifact

from factories import load_review_comments, make_deps, make_derivative_job
from email_service.orchestrator.job import run_job
from email_service.runner.fake import FakeSliceRunner


async def test_full_derivative_job_two_slices_ten_requirements() -> None:
    runner = FakeSliceRunner(comments=load_review_comments())
    deps = make_deps(runner=runner)
    job = await make_derivative_job(deps.blob_store)

    record = await run_job(job, deps)

    assert record.status == "done"
    assert record.job_id == job.job_id
    assert record.document is not None
    # review.yaml: R-01 and R-04 fail, the other 8 pass.
    assert record.summary["pass"] == 8
    assert record.summary["fail"] == 2
    assert record.unverified == []


async def test_runner_dispatched_exactly_two_slices_in_order() -> None:
    runner = FakeSliceRunner(comments=load_review_comments())
    deps = make_deps(runner=runner)
    job = await make_derivative_job(deps.blob_store)

    await run_job(job, deps)

    assert [call.slice_id for call in runner.calls] == ["slice-01", "slice-02"]
    first, second = runner.calls
    assert [r.id for r in first.requirements] == [f"R-{i:02d}" for i in range(1, 7)]
    assert [r.id for r in second.requirements] == [f"R-{i:02d}" for i in range(7, 11)]


async def test_slice_two_sees_slice_ones_committed_comments() -> None:
    """Sequential commit order: slice N reads the artifact as slice N-1 left it."""
    runner = FakeSliceRunner(comments=load_review_comments())
    deps = make_deps(runner=runner)
    job = await make_derivative_job(deps.blob_store)

    await run_job(job, deps)

    _first, second = runner.calls
    assert isinstance(second.artifact, DerivativeArtifact)
    seen_ids = {c.requirement_id for c in second.artifact.comments}
    assert seen_ids == {f"R-{i:02d}" for i in range(1, 7)}  # exactly slice 1's output


async def test_final_artifact_has_all_ten_comments_committed() -> None:
    runner = FakeSliceRunner(comments=load_review_comments())
    deps = make_deps(runner=runner)
    job = await make_derivative_job(deps.blob_store)

    await run_job(job, deps)

    artifact, cursor, version = await deps.artifact_repo.load(job.job_id)
    assert isinstance(artifact, DerivativeArtifact)
    assert {c.requirement_id for c in artifact.comments} == {f"R-{i:02d}" for i in range(1, 11)}
    assert cursor.slice_index == 1  # last (second, 0-indexed) slice committed
    assert version == 2  # one commit per slice
