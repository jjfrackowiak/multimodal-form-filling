"""Brief DoD 11: `UsagePlugin` totals asserted against a scripted `usage_metadata`, and a
slice that exceeds its budget short-circuits in `before_model_callback` rather than calling
out — exercised end to end through `run_slice`, because that is the behaviour that
actually matters (a unit test of the plugin's callbacks in isolation could pass while the
wiring into `run_slice`/`App` was still broken).
"""

from __future__ import annotations

from golden import GOLDEN_REQUIREMENTS, golden_artifact, golden_slice_request, make_comment
from google.adk.agents import LlmAgent
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from editor_service.llm.deps import EditorDeps
from editor_service.llm.output import SliceTurnOutput
from editor_service.llm.plugins import UsagePlugin
from editor_service.llm.run import run_slice
from mff_fakes import FakeLlm

TWO_REQUIREMENTS = GOLDEN_REQUIREMENTS[:2]  # R-01, R-02


def _agent(fake: FakeLlm) -> LlmAgent:
    return LlmAgent(
        name="reviewer", model=fake, instruction="x", output_schema=SliceTurnOutput, tools=[]
    )


async def test_usage_totals_and_budget_short_circuit() -> None:
    # Attempt 1: answers only R-01, leaving R-02 pending, and reports 1500 tokens used —
    # already over the 1000-token budget below.
    turn1 = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(text=SliceTurnOutput(comments=[make_comment("R-01")]).model_dump_json())
            ],
        ),
        usage_metadata=types.GenerateContentResponseUsageMetadata(total_token_count=1500),
    )
    # Attempts 2 and 3 must never be reached: the plugin should short-circuit them in
    # before_model_callback. If FakeLlm's script were consumed for either, the run would
    # raise "script exhausted" instead of returning — proof by construction.
    fake = FakeLlm.script([turn1])

    usage_plugin = UsagePlugin(budget=1000)
    deps = EditorDeps(
        artifact=golden_artifact(),
        agent=_agent(fake),
        usage_plugin=usage_plugin,
        token_budget=1000,
    )
    req = golden_slice_request(requirements=TWO_REQUIREMENTS)

    report = await run_slice(req, deps)

    # The real call happened exactly once; attempts 2 and 3 were refused before dispatch.
    assert len(fake.requests) == 1
    assert usage_plugin.total_tokens == 1500
    assert usage_plugin.calls == 1
    assert usage_plugin.budget_exceeded is True
    assert usage_plugin.blocked_calls == 2  # attempts 2 and 3, both short-circuited

    assert report.attempts_used == 3
    assert {c.requirement_id for c in report.comments} == {"R-01"}
    assert report.unverified == ["R-02"]

    # The same plugin instance is handed back for inspection either way.
    assert deps.usage_plugin is usage_plugin


async def test_usage_plugin_created_by_run_slice_is_still_reachable_after() -> None:
    """When `deps.usage_plugin` is left `None`, `run_slice` builds one from
    `deps.token_budget` and writes it back — so a caller never has to pre-construct one
    just to read totals afterwards."""
    turn_output = SliceTurnOutput(comments=[make_comment(r.id) for r in TWO_REQUIREMENTS])
    scripted = LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=turn_output.model_dump_json())]),
        usage_metadata=types.GenerateContentResponseUsageMetadata(total_token_count=42),
    )
    fake = FakeLlm.script([scripted])
    deps = EditorDeps(artifact=golden_artifact(), agent=_agent(fake), token_budget=10_000)
    assert deps.usage_plugin is None

    await run_slice(golden_slice_request(requirements=TWO_REQUIREMENTS), deps)

    assert deps.usage_plugin is not None
    assert deps.usage_plugin.total_tokens == 42
    assert deps.usage_plugin.budget_exceeded is False
