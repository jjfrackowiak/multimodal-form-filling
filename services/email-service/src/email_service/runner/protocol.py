"""`SliceRunner` — one HTTP call to the editor service, from the orchestrator's side.

A Protocol, not a client class: the orchestrator is written and tested against this
shape alone. The real implementation (an HTTP client for `POST /slices:run`) is B8's;
dispatching through this Protocol is what lets the whole orchestrator be exercised
end-to-end with `runner.fake.FakeSliceRunner` — no editor service, no HTTP, no model.

Retry and per-requirement validation are NOT modeled here. The editor service owns
them and returns a `SliceReport` that is always well-formed by the time it crosses this
boundary — complete, or complete-with-`unverified`. A caller of `run` accepts the
report as-is; it never re-dispatches on a partial or invalid result, because no such
result can arrive (see `orchestrator.job.run_job`).
"""

from __future__ import annotations

from typing import Protocol

from mff_contracts import SliceReport, SliceRequest

__all__ = ["SliceRunner"]


class SliceRunner(Protocol):
    async def run(self, request: SliceRequest) -> SliceReport: ...
