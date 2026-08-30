"""Slices — reqs 11, 16, 17.

The retry loop lives inside the editor's run, not across the wire: a `SliceReport` is
always well-formed by the time it leaves a run, so no retry state (a pending list, a
validator error, a message history) crosses the boundary that this contract describes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .artifacts import Artifact
from .docmodel import DraftOp
from .jobs import Mode
from .requirements import Requirement
from .review import ReviewComment

__all__ = ["SliceReport", "SliceRequest"]


class SliceRequest(BaseModel):
    job_id: str
    slice_id: str
    mode: Mode
    requirements: list[Requirement]
    artifact: Artifact  # CURRENT: includes prior slices' committed work
    scope_ids: list[str] = Field(default_factory=list)  # node ids or section ids


class SliceReport(BaseModel):
    slice_id: str
    comments: list[ReviewComment] = Field(default_factory=list)  # one per requirement, complete
    ops: list[DraftOp] = Field(default_factory=list)  # net-new only; empty for derivative
    unverified: list[str] = Field(default_factory=list)  # exhausted their three attempts (req 17)
    attempts_used: int = Field(ge=1)  # telemetry
