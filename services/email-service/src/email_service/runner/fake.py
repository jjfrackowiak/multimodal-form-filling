"""`FakeSliceRunner` — the `SliceRunner` double this branch tests the orchestrator
against, and the same double B9's end-to-end test uses: no editor service, no HTTP, no
model.

Two ways to drive it:

- `comments`: a `requirement_id -> ReviewComment` table (the common case — canned
  verdicts, typically built from a fixture's `review.yaml`). A `SliceRequest` is
  answered with exactly the comments its own `requirements` cover; a requirement with
  no entry in the table is silently dropped from the report, which is deliberate — it
  is how a test proves the orchestrator's completeness check catches a missing
  requirement rather than the fake papering over it.
- `handler`: full control, for what the table can't express — a slice that raises (to
  simulate a crash for a resume test), one that returns `unverified`, one keyed by
  `request.job_id` for a multi-job scenario.

Every dispatched `SliceRequest` is recorded on `.calls`, in call order, so a test can
assert not just *what* ran but *when* — e.g. that slice N's `request.artifact` already
carries what slice N-1 committed, or that a slice was invoked exactly once (proving no
retry loop exists around this Protocol).
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from mff_contracts import DraftOp, ReviewComment, SliceReport, SliceRequest

__all__ = ["FakeSliceRunner"]

Handler = Callable[[SliceRequest], "SliceReport | Awaitable[SliceReport]"]


@dataclass
class FakeSliceRunner:
    comments: dict[str, ReviewComment] | None = None
    ops: dict[str, list[DraftOp]] | None = None  # requirement_id -> DraftOps (net-new only)
    handler: Handler | None = None
    attempts_used: int = 1
    calls: list[SliceRequest] = field(default_factory=list)

    def __post_init__(self) -> None:
        if (self.comments is None) == (self.handler is None):
            raise ValueError(
                "FakeSliceRunner needs exactly one of `comments` or `handler` (got "
                f"comments={self.comments!r}, handler={self.handler!r})"
            )

    async def run(self, request: SliceRequest) -> SliceReport:
        self.calls.append(request)
        if self.handler is not None:
            result = self.handler(request)
            if inspect.isawaitable(result):
                return await result
            assert isinstance(result, SliceReport)
            return result
        return self._from_table(request)

    def _from_table(self, request: SliceRequest) -> SliceReport:
        assert self.comments is not None
        comments: list[ReviewComment] = []
        ops: list[DraftOp] = []
        unverified: list[str] = []
        for requirement in request.requirements:
            comment = self.comments.get(requirement.id)
            if comment is None:
                continue  # dropped on purpose — see module docstring
            comments.append(comment)
            if comment.verdict == "unverified":
                unverified.append(requirement.id)
            if self.ops is not None:
                ops.extend(self.ops.get(requirement.id, []))
        return SliceReport(
            slice_id=request.slice_id,
            comments=comments,
            ops=ops,
            unverified=unverified,
            attempts_used=self.attempts_used,
        )
