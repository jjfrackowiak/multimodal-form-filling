"""Usage accounting is a plugin — ADK has no `UsageLimits`.

`UsagePlugin` sums `llm_response.usage_metadata` in `after_model_callback` and refuses the
call in `before_model_callback` once the slice budget is spent, by returning an
`LlmResponse` that short-circuits the real call (ADK never dispatches to the model when a
`before_model_callback` returns non-`None` — see `tests/llm/test_usage_plugin.py`, which
asserts this against `FakeLlm.requests`, not just against the plugin's own counters).

There is no per-job ceiling yet (D5, deferred) — keeping the accounting in one plugin is
what makes adding one later a change in one place rather than a scattered one.
"""

from __future__ import annotations

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types

__all__ = ["UsagePlugin"]

_BUDGET_ERROR_CODE = "slice_budget_exceeded"


class UsagePlugin(BasePlugin):
    """Per-slice token accounting and enforcement.

    One instance per slice run (see `EditorDeps.usage_plugin`) — its counters are the
    slice's totals, not the process's, so a fresh instance per `run_slice` call is
    deliberate, not an oversight.
    """

    def __init__(self, *, budget: int, name: str = "usage") -> None:
        super().__init__(name=name)
        self.budget = budget
        self.total_tokens = 0
        self.calls = 0
        self.blocked_calls = 0

    @property
    def budget_exceeded(self) -> bool:
        return self.total_tokens >= self.budget

    async def before_model_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> LlmResponse | None:
        if not self.budget_exceeded:
            return None
        self.blocked_calls += 1
        return LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="")]),
            error_code=_BUDGET_ERROR_CODE,
            error_message=(
                f"Slice token budget of {self.budget} exhausted after {self.total_tokens} "
                "tokens; refusing to call the model again this slice."
            ),
        )

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> LlmResponse | None:
        self.calls += 1
        usage = llm_response.usage_metadata
        if usage is not None and usage.total_token_count is not None:
            self.total_tokens += usage.total_token_count
        return None
