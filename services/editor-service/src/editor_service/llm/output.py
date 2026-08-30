"""The turn-level output shape `run_slice` knows how to consume.

`SliceRequest`/`SliceReport` (mff_contracts) are the wire contract for a whole slice run —
comments settled across as many as three attempts, plus `unverified` and `attempts_used`.
Neither is what a single model turn produces: a turn only ever answers the requirements it
was asked about *this* attempt, and it never emits its own retry bookkeeping (that is
`run_slice`'s job, not the model's).

`SliceTurnOutput` is that per-turn shape — the one both flows (B6 derivative review, B7
net-new composition) must set as `build_agent(output_schema=...)` so the generic retry
loop in `run.py` can parse a turn back into `ReviewComment`s. `ops` (`DraftOp`s) are
deliberately absent here: net-new mutation tools append to `EditorDeps.op_log` as they run
(see the brief, "Where the artifact lives"), so a `DraftOp` never round-trips through
structured JSON output at all.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from mff_contracts import ReviewComment

__all__ = ["SliceTurnOutput"]


class SliceTurnOutput(BaseModel):
    """One model turn's answer: a `ReviewComment` for every requirement it settled.

    A turn need not answer every requirement it was asked about — `run.validate` decides,
    deterministically, which comments count as settled and carries the rest into the next
    attempt's prompt. An empty list is a valid (if useless) turn, not a schema violation.
    """

    comments: list[ReviewComment] = Field(default_factory=list)
