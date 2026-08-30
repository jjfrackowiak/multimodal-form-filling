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

from pydantic import BaseModel, Field

from .blobs import BlobRef, JobImage
from .requirements import Requirement

__all__ = [
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
    """The email — owns delivery."""

    request_id: str
    mode: Mode
    manifest_raw: str
    requirements: list[Requirement] = Field(default_factory=list)  # parsed ONCE per request
    job_ids: list[str] = Field(default_factory=list)  # one per form
    reply_to: str
    original_message_id: str  # delivery threads on the ORIGINAL message
    status: Literal["running", "delivered", "failed"]


class JobRequest(BaseModel):
    """orchestrator -> runner. ONE form."""

    job_id: str
    request_id: str
    mode: Mode
    form: BlobRef | None = None  # None for net-new: nothing supplied
    form_id: str
    requirements: list[Requirement] = Field(default_factory=list)  # already filtered by applies_to
    images: list[JobImage] = Field(default_factory=list)  # already scoped to this form


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
