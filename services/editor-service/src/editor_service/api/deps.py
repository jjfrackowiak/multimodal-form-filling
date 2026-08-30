"""Dependency providers for the HTTP surface.

`get_slice_runner` is the seam between this service's wiring (`llm.run_slice`,
`llm.build_agent`) and a mode-specific agent (B6's derivative reviewer, B7's net-new
composer) — this branch owns neither prompt nor tool factory (see the brief, "Out of
scope"), so the default provider below is a placeholder that names exactly what is
missing rather than silently building a agent with an invented instruction. B6/B7 replace
it with a real one; tests override it with `app.dependency_overrides` and a `FakeLlm`-
backed runner (see `tests/llm/test_api.py`), the same pattern `vision_stub.api.deps` uses
for `get_analysis_service`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from mff_contracts import SliceReport, SliceRequest

__all__ = ["SliceRunner", "get_slice_runner"]

SliceRunner = Callable[[SliceRequest], Awaitable[SliceReport]]


async def _unwired_slice_runner(_req: SliceRequest) -> SliceReport:
    raise NotImplementedError(
        "No slice runner is wired yet: build_agent's instruction and tools are B6's "
        "(derivative review) and B7's (net-new composition) to supply, not this "
        "branch's. Override editor_service.api.deps.get_slice_runner (via "
        "app.dependency_overrides, e.g.) with one that builds an EditorDeps and an "
        "LlmAgent for the request's mode and calls editor_service.llm.run_slice."
    )


def get_slice_runner() -> SliceRunner:
    return _unwired_slice_runner
