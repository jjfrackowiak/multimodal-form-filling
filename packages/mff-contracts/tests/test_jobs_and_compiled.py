"""Job lifecycle (reqs 1,2,3,6,7,8,10) and the compiled-output models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mff_contracts import (
    BlobRef,
    ClientInputs,
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

SOURCE = BlobRef(
    uri="gs://bucket/jobs/j-1/source/abc",
    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes=1024,
    sha256="abc123",
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
        manifest_raw="Under the bonnet",
        reply_to="client@example.com",
        original_message_id="<msg-1@mail>",
        status="running",
    )
    assert record.job_ids == []
    assert record.requirements == []


def test_job_request_derivative_carries_form_and_no_inputs() -> None:
    request = JobRequest(
        job_id="j-1", request_id="req-1", mode=Mode.DERIVATIVE, form_id="form-1", form=SOURCE
    )
    assert request.form == SOURCE
    assert request.inputs is None
    assert request.images == []


def test_job_request_net_new_carries_inputs_and_no_form() -> None:
    inputs = ClientInputs(
        set_id="folder-1", texts={"notes.txt": "Vehicle returned in good condition."}
    )
    request = JobRequest(
        job_id="j-1", request_id="req-1", mode=Mode.NET_NEW, form_id="folder-1", inputs=inputs
    )
    assert request.form is None
    assert request.inputs is not None
    assert request.inputs.texts["notes.txt"] == "Vehicle returned in good condition."


def test_client_inputs_round_trips_utf8_text() -> None:
    polish = "The dashboard shows a gearbox-fault message."
    inputs = ClientInputs(set_id="folder-1", texts={"notes.txt": polish})
    dumped = inputs.model_dump_json()
    restored = ClientInputs.model_validate_json(dumped)
    assert restored.texts["notes.txt"] == polish


@pytest.mark.parametrize(
    ("mode", "kwargs"),
    [
        pytest.param(
            Mode.DERIVATIVE,
            {"form": SOURCE, "inputs": ClientInputs(set_id="folder-1")},
            id="derivative-with-inputs",
        ),
        pytest.param(Mode.DERIVATIVE, {}, id="derivative-with-neither"),
        pytest.param(
            Mode.NET_NEW,
            {"form": SOURCE, "inputs": ClientInputs(set_id="folder-1")},
            id="net-new-with-form",
        ),
        pytest.param(Mode.NET_NEW, {}, id="net-new-with-neither"),
    ],
)
def test_job_request_rejects_mode_payload_mismatch(mode: Mode, kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="JobRequest: mode is"):
        JobRequest(job_id="j-1", request_id="req-1", mode=mode, form_id="form-1", **kwargs)


def test_mixed_request_covers_derivative_and_net_new_jobs_together() -> None:
    """The case the change exists for: one client email, one RequestRecord, both modes."""
    derivative_jobs = [
        JobRequest(
            job_id=f"j-d{i}",
            request_id="req-1",
            mode=Mode.DERIVATIVE,
            form_id=f"form-{i}.docx",
            form=SOURCE,
        )
        for i in range(3)
    ]
    net_new_jobs = [
        JobRequest(
            job_id=f"j-n{i}",
            request_id="req-1",
            mode=Mode.NET_NEW,
            form_id=f"folder-{i}",
            inputs=ClientInputs(set_id=f"folder-{i}", texts={"notes.txt": "body text"}),
        )
        for i in range(4)
    ]
    all_jobs = derivative_jobs + net_new_jobs
    record = RequestRecord(
        request_id="req-1",
        manifest_raw="Under the bonnet",
        job_ids=[job.job_id for job in all_jobs],
        reply_to="client@example.com",
        original_message_id="<msg-1@mail>",
        status="running",
    )
    assert len(record.job_ids) == 7
    assert sum(1 for job in all_jobs if job.mode == Mode.DERIVATIVE) == 3
    assert sum(1 for job in all_jobs if job.mode == Mode.NET_NEW) == 4


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
