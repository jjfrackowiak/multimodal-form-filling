"""Job lifecycle — reqs 1, 2, 3, 6, 7, 8, 10.

Requirements and images arrive at a `JobRequest` **already scoped**: `applies_to` and
image-to-form assignment are resolved once by the orchestrator rather than by every runner.

`JobCursor` travels inside the artifact write: committing a slice's result and advancing
the cursor must be one transaction, or a crash between them either replays a slice
(duplicate comments) or skips one (silently missing requirements).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .blobs import BlobRef, JobImage
from .requirements import Requirement

__all__ = [
    "ClientInputs",
    "IntakeProblem",
    "IntakeVerdict",
    "JobCursor",
    "JobRecord",
    "JobRequest",
    "Mode",
    "RequestAccepted",
    "RequestRecord",
    "RequestResult",
]


class Mode(StrEnum):
    DERIVATIVE = "derivative"
    NET_NEW = "net_new"


class IntakeProblem(BaseModel):
    code: str
    detail: str  # req 8: exactly what to add or change


class IntakeVerdict(BaseModel):
    valid: bool
    problems: list[IntakeProblem] = Field(default_factory=list)


class RequestRecord(BaseModel):
    """The email — owns delivery.

    The manifest always comes from the email body, never from an attachment. A request is
    a bag of work items, and each item (`JobRequest`) knows its own mode — a single email
    can carry both derivative and net-new jobs at once, so no request-level mode exists.
    """

    request_id: str
    manifest_raw: str
    requirements: list[Requirement] = Field(default_factory=list)  # parsed ONCE per request
    job_ids: list[str] = Field(default_factory=list)  # one per form
    reply_to: str
    original_message_id: str  # delivery threads on the ORIGINAL message
    status: Literal["running", "delivered", "failed"]


class ClientInputs(BaseModel):
    """One set of net-new inputs — one folder inside the net-new zip."""

    set_id: str  # the folder name; the client's own label
    texts: dict[str, str] = Field(default_factory=dict)  # filename -> UTF-8 content


class JobRequest(BaseModel):
    """orchestrator -> runner. ONE form.

    `mode` is per-job — the authority on what kind of work this is — and the model
    validator below keeps it structurally paired with the right payload: derivative jobs
    carry `form` and never `inputs`; net-new jobs carry `inputs` and never `form`.
    """

    job_id: str
    request_id: str
    mode: Mode
    form_id: str  # .docx filename, or input folder name
    form: BlobRef | None = None  # derivative only
    inputs: ClientInputs | None = None  # net-new only
    requirements: list[Requirement] = Field(default_factory=list)  # already filtered by applies_to
    images: list[JobImage] = Field(default_factory=list)  # already scoped to this form

    @model_validator(mode="after")
    def _mode_matches_payload(self) -> JobRequest:
        if self.mode == Mode.DERIVATIVE:
            if self.form is None:
                raise ValueError("JobRequest: mode is derivative but form is not set")
            if self.inputs is not None:
                raise ValueError("JobRequest: mode is derivative but inputs is set")
        elif self.mode == Mode.NET_NEW:
            if self.inputs is None:
                raise ValueError("JobRequest: mode is net_new but inputs is not set")
            if self.form is not None:
                raise ValueError("JobRequest: mode is net_new but form is set")
        return self


class RequestAccepted(BaseModel):
    """The 202 — req 7 quotes exactly this."""

    request_id: str
    requirements: list[Requirement] = Field(default_factory=list)


class JobCursor(BaseModel):
    """W1: written WITH the artifact, atomically."""

    slice_index: int


class JobRecord(BaseModel):
    """Small, pollable — answers D2."""

    job_id: str
    request_id: str
    form_id: str
    status: Literal["running", "done", "failed"]
    cursor: JobCursor
    document: BlobRef | None = None
    summary: dict[str, int] = Field(default_factory=dict)
    unverified: list[str] = Field(default_factory=list)
    failure_detail: str | None = None


class RequestResult(BaseModel):
    """-> delivery, once ALL jobs settle."""

    request_id: str
    status: Literal["done", "partial", "failed"]
    documents: list[BlobRef] = Field(default_factory=list)  # one per successful job
    requirements: list[Requirement] = Field(default_factory=list)  # ships WITH the result
    summary: dict[str, int] = Field(default_factory=dict)
    unverified: list[str] = Field(default_factory=list)  # req 17, named explicitly
    failed_forms: list[str] = Field(default_factory=list)
