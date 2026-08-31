"""A net-new job walked end-to-end, mirroring `test_end_to_end.py`'s derivative
coverage — the mixed-request DoD item only checks artifact *type*; this exercises a
full `NetNewArtifact` job through slices, completeness and compile.
"""

from __future__ import annotations

from factories import load_requirements, make_deps, make_netnew_job

from email_service.orchestrator.job import run_job
from email_service.runner.fake import FakeSliceRunner
from mff_contracts import Anchor, DraftOp, NetNewArtifact, ReviewComment, SliceReport, SliceRequest


async def test_net_new_job_composes_entries_and_completes() -> None:
    requirements = load_requirements()

    def handler(request: SliceRequest) -> SliceReport:
        comments = [
            ReviewComment(
                requirement_id=r.id,
                anchor=Anchor(kind="document"),
                verdict="realised",
                justification=f"composed from client inputs for {r.id}",
            )
            for r in request.requirements
        ]
        ops = [
            DraftOp(
                kind="set",
                requirement_id=r.id,
                entry_id=f"entry-{r.id}",
                value=f"value for {r.id}",
            )
            for r in request.requirements
        ]
        return SliceReport(
            slice_id=request.slice_id, comments=comments, ops=ops, unverified=[], attempts_used=1
        )

    runner = FakeSliceRunner(handler=handler)
    deps = make_deps(runner=runner)
    job = make_netnew_job(requirements=requirements)

    record = await run_job(job, deps)

    assert record.status == "done"
    assert record.summary["realised"] == 10
    assert record.document is not None

    artifact, cursor, version = await deps.artifact_repo.load(job.job_id)
    assert isinstance(artifact, NetNewArtifact)
    assert cursor.slice_index == 1
    assert version == 2
    entries = [e for s in artifact.draft.sections for e in s.entries]
    assert {e.set_by for e in entries if e.value} == {r.id for r in requirements}
    assert {e.value for e in entries if e.value} == {f"value for {r.id}" for r in requirements}
