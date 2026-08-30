"""One agent factory. Both flows (B6 derivative review, B7 net-new composition) call this
rather than constructing `LlmAgent` themselves — it is the one place `EDITOR_MODEL_ID`
gets turned into a live `Gemini` client (see `llm.model.build_editor_model`).

Structured output and tools together, on the same agent: ADK sorts out whether the schema
goes straight onto the request or the model needs the `set_model_response` tool fallback
(`_OutputSchemaRequestProcessor`) — see `tests/llm/test_build_agent.py` for the behaviour
this rests on. Do not hand-roll a formatter sub-agent, and do not split the agent in two.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from pydantic import BaseModel

from editor_service.llm.model import build_editor_model
from editor_service.settings import Settings, get_settings

__all__ = ["BaseLlm", "build_agent"]


def build_agent(
    *,
    name: str,
    output_schema: type[BaseModel],
    instruction: str,
    tools: list[Callable[..., Any]],
    settings: Settings | None = None,
    model: BaseLlm | None = None,
) -> LlmAgent:
    """Build the one kind of `LlmAgent` this service ever runs.

    `settings`/`model` are keyword-only extensions beyond the brief's own signature, added
    for testability without a second construction path: `model` lets a test hand in
    `FakeLlm` directly (see `mff_fakes.FakeLlm`) instead of resolving real ADC credentials,
    and `settings` lets a test supply a `Settings` object without real environment
    variables. Neither is read unless `model` is omitted — production callers (B6/B7) pass
    neither and get the real `EDITOR_MODEL_ID` Gemini client, resolved from
    `Settings.from_env()`.
    """
    resolved_model: str | BaseLlm
    if model is not None:
        resolved_model = model
    else:
        resolved_settings = settings or get_settings()
        resolved_model = build_editor_model(resolved_settings)

    return LlmAgent(
        name=name,
        model=resolved_model,
        instruction=instruction,
        output_schema=output_schema,
        tools=list(tools),
    )
