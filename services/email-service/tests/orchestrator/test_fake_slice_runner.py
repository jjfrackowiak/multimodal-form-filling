"""Unit tests for `runner.fake.FakeSliceRunner` — the double this branch (and B9's
end-to-end test) run the orchestrator against.
"""

from __future__ import annotations

import pytest
from factories import load_requirements

from email_service.runner.fake import FakeSliceRunner
from mff_contracts import Anchor, DraftOp, Mode, ReviewComment, SliceReport, SliceRequest


def _pass_comment(requirement_id: str) -> ReviewComment:
    return ReviewComment(
        requirement_id=requirement_id,
        anchor=Anchor(kind="document"),
        verdict="pass",
        justification="fine",
    )


def _slice_request(requirement_ids: list[str]) -> SliceRequest:
    from mff_contracts import BlobRef, DerivativeArtifact

    requirements = [r for r in load_requirements() if r.id in requirement_ids]
    artifact = DerivativeArtifact(
        job_id="j-1",
        form_id="f-1",
        source=BlobRef(uri="gs://x/y", content_type="a/b", size_bytes=1, sha256="0" * 64),
    )
    return SliceRequest(
        job_id="j-1",
        slice_id="slice-01",
        mode=Mode.DERIVATIVE,
        requirements=requirements,
        artifact=artifact,
        scope_ids=[],
    )


def test_needs_exactly_one_of_comments_or_handler() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        FakeSliceRunner()
    with pytest.raises(ValueError, match="exactly one"):
        FakeSliceRunner(
            comments={"R-01": _pass_comment("R-01")},
            handler=lambda r: SliceReport(
                slice_id=r.slice_id, comments=[], ops=[], unverified=[], attempts_used=1
            ),
        )


async def test_table_driven_run_records_calls_and_answers_only_requested_requirements() -> None:
    runner = FakeSliceRunner(
        comments={"R-01": _pass_comment("R-01"), "R-02": _pass_comment("R-02")}
    )
    request = _slice_request(["R-01", "R-02"])

    report = await runner.run(request)

    assert runner.calls == [request]
    assert {c.requirement_id for c in report.comments} == {"R-01", "R-02"}
    assert report.slice_id == "slice-01"
    assert report.attempts_used == 1


async def test_table_driven_run_silently_drops_requirements_missing_from_the_table() -> None:
    runner = FakeSliceRunner(comments={"R-01": _pass_comment("R-01")})
    request = _slice_request(["R-01", "R-02"])

    report = await runner.run(request)

    assert {c.requirement_id for c in report.comments} == {"R-01"}


async def test_table_driven_run_reports_unverified_requirement_ids() -> None:
    unverified_comment = ReviewComment(
        requirement_id="R-01",
        anchor=Anchor(kind="document"),
        verdict="unverified",
        justification="could not verify",
    )
    runner = FakeSliceRunner(comments={"R-01": unverified_comment})
    request = _slice_request(["R-01"])

    report = await runner.run(request)

    assert report.unverified == ["R-01"]


async def test_table_driven_run_emits_ops_from_the_ops_table() -> None:
    op = DraftOp(kind="append", requirement_id="R-01", section_id="draft", value="x")
    runner = FakeSliceRunner(comments={"R-01": _pass_comment("R-01")}, ops={"R-01": [op]})
    request = _slice_request(["R-01"])

    report = await runner.run(request)

    assert report.ops == [op]


async def test_sync_handler_is_supported_and_calls_are_recorded() -> None:
    def handler(request: SliceRequest) -> SliceReport:
        return SliceReport(
            slice_id=request.slice_id, comments=[], ops=[], unverified=[], attempts_used=3
        )

    runner = FakeSliceRunner(handler=handler)
    request = _slice_request(["R-01"])

    report = await runner.run(request)

    assert report.attempts_used == 3
    assert runner.calls == [request]


async def test_async_handler_is_awaited() -> None:
    async def handler(request: SliceRequest) -> SliceReport:
        return SliceReport(
            slice_id=request.slice_id, comments=[], ops=[], unverified=[], attempts_used=1
        )

    runner = FakeSliceRunner(handler=handler)
    request = _slice_request(["R-01"])

    report = await runner.run(request)

    assert report.slice_id == "slice-01"
