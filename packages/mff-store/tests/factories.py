"""Small builders for contract objects, shared by the test modules."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from mff_contracts import (
    BlobRef,
    DerivativeArtifact,
    FormDraft,
    JobCursor,
    JobRecord,
    NetNewArtifact,
    RequestRecord,
)

# tests/ -> mff-store/ -> packages/ -> repo root. Location-based, not cwd-based, so it
# is correct regardless of where `pytest`/`make check` is invoked from.
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "fixtures" / "fleet-vehicle-return"


def make_source_ref(form_id: str = "form_supplied.docx") -> BlobRef:
    return BlobRef(
        uri=f"gs://mff-local/source/{form_id}",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=1,
        sha256="0" * 64,
    )


def make_artifact(form_id: str = "job-1") -> DerivativeArtifact:
    return DerivativeArtifact(
        job_id="j-1", form_id=form_id, source=make_source_ref(form_id), nodes=[], comments=[]
    )


def make_netnew_artifact(form_id: str = "WN-7020U") -> NetNewArtifact:
    return NetNewArtifact(job_id="j-1", form_id=form_id, draft=FormDraft(), comments=[])


def make_cursor(slice_index: int = 0) -> JobCursor:
    return JobCursor(slice_index=slice_index)


def make_job_record(
    job_id: str = "job-1",
    request_id: str = "req-1",
    *,
    status: Literal["running", "done", "failed"] = "running",
) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        request_id=request_id,
        form_id=job_id,
        status=status,
        cursor=make_cursor(),
    )


def make_request_record(request_id: str = "req-1") -> RequestRecord:
    return RequestRecord(
        request_id=request_id,
        manifest_raw="16 zdjęć,\nPod maską\n",
        requirements=[],
        job_ids=["job-1"],
        reply_to="client@example.test",
        original_message_id="<abc@example.test>",
        status="running",
    )
