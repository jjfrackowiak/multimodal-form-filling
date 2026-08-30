"""A net-new job walked end-to-end, mirroring `test_end_to_end.py`'s derivative
coverage — the mixed-request DoD item only checks artifact *type*; this exercises a
full `NetNewArtifact` job through slices, completeness and compile.
"""

from __future__ import annotations

from mff_contracts import Anchor, DraftOp, NetNewArtifact, ReviewComment, SliceReport, SliceRequest

from factories import load_requirements, make_deps, make_netnew_job
from email_service.orchestrator.artifacts import NET_NEW_ROOT_SECTION_ID
from email_service.orchestrator.job import run_job
from email_service.runner.fake import FakeSliceRunner


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
                kind="append",
                requirement_id=r.id,
                section_id=NET_NEW_ROOT_SECTION_ID,
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
    entries = artifact.draft.sections[0].entries
    assert len(entries) == 10
    assert {e.set_by for e in entries} == {r.id for r in requirements}
