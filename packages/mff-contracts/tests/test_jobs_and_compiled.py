"""Job lifecycle (reqs 1,2,3,6,7,8,10) and the compiled-output models."""

from __future__ import annotations

from mff_contracts import (
    BlobRef,
    CompiledForm,
    IntakeProblem,
    IntakeVerdict,
    JobCursor,
    JobRecord,
    JobRequest,
    Mode,
    RenderMap,
    RequestAccepted,
    RequestRecord,
    RequestResult,
    RunSpan,
)


def test_mode_values_are_derivative_and_net_new() -> None:
    assert Mode.DERIVATIVE.value == "derivative"
    assert Mode.NET_NEW.value == "net_new"


def test_intake_verdict_carries_actionable_problems() -> None:
    verdict = IntakeVerdict(
        valid=False,
        problems=[IntakeProblem(code="missing_manifest", detail="Attach the requirements list.")],
    )
    assert verdict.valid is False
    assert verdict.problems[0].code == "missing_manifest"


def test_request_record_owns_delivery_threading() -> None:
    record = RequestRecord(
        request_id="req-1",
        mode=Mode.DERIVATIVE,
        manifest_raw="Pod maską",
        reply_to="client@example.com",
        original_message_id="<msg-1@mail>",
        status="running",
    )
    assert record.job_ids == []
    assert record.requirements == []


def test_job_request_form_is_none_for_net_new() -> None:
    request = JobRequest(job_id="j-1", request_id="req-1", mode=Mode.NET_NEW, form_id="form-1")
    assert request.form is None
    assert request.images == []


def test_request_accepted_quotes_the_parsed_requirements() -> None:
    accepted = RequestAccepted(request_id="req-1")
    assert accepted.requirements == []


def test_job_cursor_travels_with_the_artifact() -> None:
    cursor = JobCursor(slice_index=3)
    record = JobRecord(
        job_id="j-1",
        request_id="req-1",
        form_id="form-1",
        status="running",
        cursor=cursor,
    )
    assert record.cursor.slice_index == 3
    assert record.unverified == []


def test_request_result_names_unverified_requirements_explicitly() -> None:
    result = RequestResult(
        request_id="req-1",
        status="partial",
        unverified=["R-07"],
        failed_forms=[],
    )
    assert result.unverified == ["R-07"]


def test_run_span_is_inclusive_of_run_end() -> None:
    span = RunSpan(paragraph_index=4, run_start=0, run_end=2)
    assert span.run_end == 2


def test_render_map_bridges_anchor_ids_to_run_spans() -> None:
    span = RunSpan(paragraph_index=0, run_start=0, run_end=0)
    render_map = RenderMap(anchor_to_span={"n-1": span})
    assert render_map.anchor_to_span["n-1"].paragraph_index == 0


def test_compiled_form_unanchored_makes_the_document_fallback_visible() -> None:
    blob = BlobRef(
        uri="gs://b/doc", content_type="application/octet-stream", size_bytes=1, sha256="x"
    )
    compiled = CompiledForm(
        form_id="form-1",
        document=blob,
        render_map=RenderMap(),
        comments_attached=9,
        unanchored=["R-10"],
    )
    assert compiled.unanchored == ["R-10"]
