"""DoD #7 — no retry loop exists here: a `SliceReport` carrying `unverified` is
accepted as-is, not re-dispatched.

`SliceRequest` has no `pending`/`history`/`validator_error` for exactly this reason
(see `mff_contracts.slices`) — the retry loop, if any, lives inside the editor's own
run, on the other side of the HTTP boundary this branch never crosses.
"""

from __future__ import annotations

from factories import load_requirements, load_review_comments, make_deps, make_derivative_job

from email_service.orchestrator.job import run_job
from email_service.runner.fake import FakeSliceRunner
from mff_contracts import Anchor, ReviewComment


async def test_unverified_report_is_accepted_and_never_redispatched() -> None:
    requirements = load_requirements()
    comments = dict(load_review_comments())
    # req 17: an "unverified" verdict is a well-formed, TERMINAL outcome — comments'
    # own validator requires a non-empty justification and forbids `suggestion` here.
    comments["R-05"] = ReviewComment(
        requirement_id="R-05",
        anchor=Anchor(kind="document"),
        verdict="unverified",
        justification="exhausted three attempts without a clear verdict",
    )

    runner = FakeSliceRunner(comments=comments)
    deps = make_deps(runner=runner)
    job = await make_derivative_job(deps.blob_store, requirements=requirements)

    record = await run_job(job, deps)

    assert record.status == "done"
    assert record.unverified == ["R-05"]
    # Exactly one dispatch per slice — the slice containing R-05 (slice-01) was never
    # re-run to try to resolve the unverified verdict.
    assert [call.slice_id for call in runner.calls] == ["slice-01", "slice-02"]
