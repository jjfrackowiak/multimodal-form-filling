"""SliceRequest/SliceReport — history is opaque `list[dict[str, Any]]`, never `ModelMessage`,
so this package never imports the agent framework."""

from __future__ import annotations

from mff_contracts import (
    BlobRef,
    DerivativeArtifact,
    Mode,
    Requirement,
    SliceReport,
    SliceRequest,
)

SOURCE = BlobRef(
    uri="gs://bucket/jobs/j-1/source/abc",
    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes=1024,
    sha256="abc123",
)


def _requirement() -> Requirement:
    return Requirement(
        id="R-01",
        ordinal=11,
        text="A photograph of the engine bay.",
        source_span="Pod maską",
        source_line=2,
    )


def test_slice_request_history_accepts_arbitrary_dicts() -> None:
    request = SliceRequest(
        job_id="j-1",
        slice_id="slice-01",
        mode=Mode.DERIVATIVE,
        requirements=[_requirement()],
        pending=["R-01"],
        artifact=DerivativeArtifact(form_id="form-1", source=SOURCE),
        scope_ids=["n-1"],
        history=[{"role": "user", "content": "look at the engine bay photo"}],
    )
    assert request.history[0]["role"] == "user"
    assert request.validator_error is None


def test_slice_report_ops_are_empty_for_a_derivative_run() -> None:
    report = SliceReport(
        slice_id="slice-01",
        attempt=1,
        unanswered=["R-01"],
        history=[{"role": "assistant", "content": "..."}],
    )
    assert report.ops == []
    assert report.comments == []
    assert report.unanswered == ["R-01"]
