"""Applier↔orchestrator boundary types — internal to this package (B14).

`ApplyResult`, `Overwrite` and `Rejection` are deliberately **not** in `mff_contracts`:
they describe how `apply_slice` reports back to its caller, not something that crosses a
service boundary on the wire. `mff-contracts` is frozen; these live here instead.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from mff_contracts import Artifact, DraftOp

__all__ = ["ApplyResult", "Overwrite", "Rejection"]


class Overwrite(BaseModel):
    """The D3 signal: a `set`/`delete` landed on an entry a *different* requirement wrote.

    Recorded, never blocked — a later requirement legitimately supersedes an earlier one
    sometimes. This is the only mechanical evidence that two requirements may contradict
    each other, so it is surfaced rather than swallowed.
    """

    entry_id: str
    previous_requirement: str
    new_requirement: str


class Rejection(BaseModel):
    """One `DraftOp` (or, for a caller bug, a whole report) that was refused, with why."""

    reason: str
    op: DraftOp | None = None


class ApplyResult(BaseModel):
    artifact: Artifact
    overwrites: list[Overwrite] = Field(default_factory=list)
    rejected: list[Rejection] = Field(default_factory=list)
