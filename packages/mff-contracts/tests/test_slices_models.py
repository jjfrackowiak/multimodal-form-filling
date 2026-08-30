"""SliceRequest/SliceReport — no retry state crosses the wire.

The retry loop lives inside the editor's run; a SliceReport is always well-formed by the
time it leaves one, so there is no `history`, `pending`, `validator_error`, or `attempt`
here any more — just the outcome, plus `attempts_used` as telemetry.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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


def test_slice_request_carries_no_retry_state() -> None:
    request = SliceRequest(
        job_id="j-1",
        slice_id="slice-01",
        mode=Mode.DERIVATIVE,
        requirements=[_requirement()],
        artifact=DerivativeArtifact(form_id="form-1", source=SOURCE),
        scope_ids=["n-1"],
    )
    assert request.scope_ids == ["n-1"]
    assert not hasattr(request, "history")
    assert not hasattr(request, "pending")
    assert not hasattr(request, "validator_error")


def test_slice_report_ops_are_empty_for_a_derivative_run() -> None:
    report = SliceReport(
        slice_id="slice-01",
        unverified=["R-01"],
        attempts_used=2,
    )
    assert report.ops == []
    assert report.comments == []
    assert report.unverified == ["R-01"]
    assert report.attempts_used == 2
    assert not hasattr(report, "history")
    assert not hasattr(report, "attempt")
    assert not hasattr(report, "unanswered")


def test_attempts_used_of_one_is_valid() -> None:
    report = SliceReport(slice_id="slice-01", attempts_used=1)
    assert report.attempts_used == 1


def test_attempts_used_below_one_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SliceReport(slice_id="slice-01", attempts_used=0)
