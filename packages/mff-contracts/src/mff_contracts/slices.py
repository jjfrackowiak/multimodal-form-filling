"""Slices — reqs 11, 16, 17.

`history` is typed `list[dict[str, Any]]` on both `SliceRequest` and `SliceReport` —
deliberately opaque. Typing it as the agent framework's message type would drag
`pydantic-ai` into the package everything else depends on.
"""

from __future__ import annotations

from typing import Any

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
    pending: list[str] = Field(default_factory=list)  # narrows on retry
    artifact: Artifact  # CURRENT: includes prior slices' committed work
    scope_ids: list[str] = Field(default_factory=list)  # node ids or section ids
    history: list[dict[str, Any]] = Field(default_factory=list)  # OPAQUE
    validator_error: str | None = None


class SliceReport(BaseModel):
    slice_id: str
    attempt: int
    comments: list[ReviewComment] = Field(default_factory=list)  # only for ids in `pending`
    ops: list[DraftOp] = Field(default_factory=list)  # net-new only; empty for derivative
    unanswered: list[str] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
