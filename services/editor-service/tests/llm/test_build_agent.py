"""Brief DoD 9 — "the one ADK behaviour the whole design rests on": an `LlmAgent` carrying
both `output_schema` and a non-empty `tools` list must produce a request in which the real
tools survive, whichever path ADK takes to reconcile them.

`FakeLlm.model == "fake-llm"` is not a Gemini model, so
`capabilities.output_schema_and_tools` is `False` for it (see
`google.adk.models._capabilities.gemini_output_schema_and_tools`) — meaning every test here
exercises the *fallback* path (`_OutputSchemaRequestProcessor` injecting `set_model_response`
alongside the real tools), which is the harder of the two paths to get right and the one
`FakeLlm` can actually exercise offline. The live smoke test (`test_live_smoke.py`) is what
proves the other path — real Gemini reporting the capability `True` — behaves the same way
in the one place that matters: real tools are never dropped either way.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types
from pydantic import BaseModel

from editor_service.llm.agent import build_agent
from editor_service.settings import Settings
from mff_fakes import FakeLlm


class _Out(BaseModel):
    value: str


def _dummy_tool(x: str) -> str:
    """A dummy tool, standing in for a real mutation/vision tool."""
    return x


async def _run_one_turn(agent: LlmAgent, fake: FakeLlm) -> None:
    from google.adk.apps import App
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    session_service = InMemorySessionService()
    await session_service.create_session(app_name="test-app", user_id="u", session_id="s", state={})
    runner = Runner(app=App(name="test-app", root_agent=agent), session_service=session_service)
    async for _event in runner.run_async(
        user_id="u",
        session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text="go")]),
    ):
        pass


async def test_real_tools_survive_alongside_output_schema() -> None:
    fake = FakeLlm.script([_Out(value="hello")])
    agent = LlmAgent(
        name="probe", model=fake, instruction="x", output_schema=_Out, tools=[_dummy_tool]
    )

    await _run_one_turn(agent, fake)

    assert len(fake.requests) == 1
    tool_names = set(fake.requests[-1].tools_dict.keys())
    assert "_dummy_tool" in tool_names, tool_names


async def test_fallback_tool_is_added_without_displacing_real_tools() -> None:
    """The fallback path specifically: `set_model_response` is injected, but the caller's
    own tool is never displaced by it — both are present on the final request."""
    fake = FakeLlm.script([_Out(value="hello")])
    agent = LlmAgent(
        name="probe", model=fake, instruction="x", output_schema=_Out, tools=[_dummy_tool]
    )

    await _run_one_turn(agent, fake)

    tool_names = set(fake.requests[-1].tools_dict.keys())
    assert tool_names == {"set_model_response", "_dummy_tool"}


async def test_output_schema_alone_needs_no_fallback_tool() -> None:
    """With no other tools, the schema goes straight onto the request regardless of the
    capability flag — the fallback exists only for schema-plus-tools."""
    fake = FakeLlm.script([_Out(value="hello")])
    agent = LlmAgent(name="probe", model=fake, instruction="x", output_schema=_Out, tools=[])

    await _run_one_turn(agent, fake)

    assert fake.requests[-1].tools_dict == {}


def test_build_agent_wires_name_schema_instruction_and_tools() -> None:
    fake = FakeLlm.script([])
    agent = build_agent(
        name="reviewer",
        output_schema=_Out,
        instruction="review the requirement",
        tools=[_dummy_tool],
        model=fake,
    )
    assert agent.name == "reviewer"
    assert agent.output_schema is _Out
    assert agent.instruction == "review the requirement"
    assert agent.model is fake
    assert len(agent.tools) == 1


def test_build_agent_uses_real_editor_model_when_no_override_given() -> None:
    """Without a `model=` override, `build_agent` resolves the real, ADC-authenticated
    `EDITOR_MODEL_ID` Gemini client — construction only, no network/credential touch."""
    settings = Settings.from_env({"GOOGLE_CLOUD_PROJECT": "test-project"})
    agent = build_agent(
        name="reviewer",
        output_schema=_Out,
        instruction="review the requirement",
        tools=[],
        settings=settings,
    )
    assert agent.model.model == settings.editor_model_id  # type: ignore[union-attr]
    assert type(agent.model).__name__ == "Gemini"
