"""Derivative artifacts are never mutated (req 14).

`DerivativeArtifact` has no draft: `nodes` and `source` come back as the exact same
objects, and only `comments` grows. A `SliceReport` carrying `ops` for a derivative slice
is a caller bug — the whole report is rejected, nothing is applied.
"""

from __future__ import annotations

from mff_applier import apply_slice
from mff_contracts import (
    Anchor,
    Artifact,
    BlobRef,
    DerivativeArtifact,
    DraftOp,
    Node,
    ReviewComment,
    SliceReport,
)

SOURCE = BlobRef(
    uri="gs://bucket/jobs/j-1/source/abc",
    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes=2048,
    sha256="abc123",
)


def _comment(requirement_id: str, target_id: str, verdict: str = "pass") -> ReviewComment:
    return ReviewComment(
        requirement_id=requirement_id,
        anchor=Anchor(kind="node", target_id=target_id),
        verdict=verdict,
        justification="Tyre tread photographed.",
        suggestion=("Retake the photo." if verdict == "fail" else None),
    )


def _derivative(artifact: Artifact) -> DerivativeArtifact:
    """Narrow `ApplyResult.artifact` (a union) back to `DerivativeArtifact` for assertions."""
    assert isinstance(artifact, DerivativeArtifact)
    return artifact


def _artifact() -> DerivativeArtifact:
    nodes = [
        Node(id="n-1", kind="paragraph", text="Engine bay", parent_id=None),
        Node(id="n-2", kind="image", text="", parent_id="n-1", image_sha256="deadbeef"),
    ]
    return DerivativeArtifact(job_id="j-1", form_id="form-1", source=SOURCE, nodes=nodes)


def test_comments_are_appended_nodes_and_source_are_the_same_objects() -> None:
    artifact = _artifact()
    report = SliceReport(
        slice_id="slice-01",
        comments=[_comment("R-07", "n-2")],
        attempts_used=1,
    )

    result = apply_slice(artifact, report, scope_ids=["n-1", "n-2"])

    assert result.rejected == []
    assert result.overwrites == []
    assert result.artifact is not artifact  # a new artifact object is returned
    assert _derivative(result.artifact).nodes is artifact.nodes  # but its guts are untouched
    assert _derivative(result.artifact).source is artifact.source
    assert result.artifact.comments == [_comment("R-07", "n-2")]
    assert artifact.comments == []  # the original is not mutated


def test_comments_accumulate_across_two_applications() -> None:
    artifact = _artifact()
    first = apply_slice(
        artifact,
        SliceReport(slice_id="slice-01", comments=[_comment("R-07", "n-2")], attempts_used=1),
        scope_ids=["n-1", "n-2"],
    )
    second = apply_slice(
        first.artifact,
        SliceReport(slice_id="slice-02", comments=[_comment("R-08", "n-1")], attempts_used=1),
        scope_ids=["n-1", "n-2"],
    )
    assert [c.requirement_id for c in second.artifact.comments] == ["R-07", "R-08"]
    assert _derivative(second.artifact).nodes is artifact.nodes


def test_ops_on_a_derivative_artifact_are_rejected_wholesale() -> None:
    artifact = _artifact()
    bogus_op = DraftOp(kind="append", requirement_id="R-01", section_id="sec-1")
    report = SliceReport(
        slice_id="slice-01",
        comments=[_comment("R-07", "n-2")],
        ops=[bogus_op],
        attempts_used=1,
    )

    result = apply_slice(artifact, report, scope_ids=["n-1", "n-2"])

    assert result.artifact is artifact  # nothing at all was applied
    assert result.artifact.comments == []  # not even the comments
    assert result.overwrites == []
    assert len(result.rejected) == 1
    assert result.rejected[0].op == bogus_op
    assert "never mutated" in result.rejected[0].reason


def test_multiple_ops_on_a_derivative_artifact_are_each_named_in_rejected() -> None:
    artifact = _artifact()
    ops = [
        DraftOp(kind="append", requirement_id="R-01", section_id="sec-1"),
        DraftOp(kind="delete", requirement_id="R-02", entry_id="e-1"),
    ]
    report = SliceReport(slice_id="slice-01", ops=ops, attempts_used=1)

    result = apply_slice(artifact, report, scope_ids=[])

    assert [r.op for r in result.rejected] == ops
