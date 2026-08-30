"""`EditorDeps` — what `run_slice` holds for the life of one slice.

Where the artifact lives (see the B8 brief): ADK's `session.state` is a JSON-shaped dict
committed as a `state_delta` on every event, so the `Artifact` — large, live, and mutated
in place by tools between model calls — cannot live there without serialising the whole
document on every tool call. It lives here instead, and mutation tools (B6/B7's, not this
module's) come from a factory that closes over one `EditorDeps` instance and appends a
`DraftOp` to `op_log` as they mutate.

`session.state` itself carries only the scalars `run.py`'s prompt templates interpolate
(`slice_id`, requirement count) — never the artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from google.adk.agents import LlmAgent
from google.adk.sessions import BaseSessionService, InMemorySessionService

from editor_service.llm.plugins import UsagePlugin
from mff_contracts import Artifact, DraftOp

__all__ = ["EditorDeps"]

# No per-job ceiling yet — that is D5, deferred (see the brief). This is a generous
# per-slice placeholder so `UsagePlugin` has something to enforce today, and changing it
# later is a one-line change in one place.
DEFAULT_SLICE_TOKEN_BUDGET = 200_000


@dataclass
class EditorDeps:
    """Everything a slice run needs beyond the `SliceRequest` itself.

    `agent` is built by the caller (B6/B7, via `llm.agent.build_agent`) — `run_slice` does
    not build it, it only runs it. Sessions are ours, in memory, per slice: the default
    `InMemorySessionService` exists only for the life of a slice run, never reused as a job-
    or request-level store (that is B12's job, not this service's).
    """

    artifact: Artifact
    agent: LlmAgent
    op_log: list[DraftOp] = field(default_factory=list)
    session_service: BaseSessionService = field(default_factory=InMemorySessionService)
    token_budget: int = DEFAULT_SLICE_TOKEN_BUDGET
    #: Supply a pre-built plugin to inspect totals after `run_slice` returns; `run_slice`
    #: creates one from `token_budget` when this is left `None` and writes it back here, so
    #: the caller can always read `deps.usage_plugin` afterwards either way.
    usage_plugin: UsagePlugin | None = None
