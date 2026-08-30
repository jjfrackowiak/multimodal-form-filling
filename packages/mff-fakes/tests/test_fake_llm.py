"""Tests for `FakeLlm` against its own package only — no fixture, no other package.

Runs the fake through the real integration path (`LlmAgent` + `InMemoryRunner`) rather
than calling `generate_content_async` in isolation wherever that path is what a consumer
actually exercises — a unit test that bypasses ADK's own plumbing would not catch a
mismatch with how `LlmAgent` actually calls a `BaseLlm`.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from google.adk.agents import LlmAgent
from google.adk.events.event import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.adk.tools.function_tool import FunctionTool
from google.genai import types
from pydantic import BaseModel

from mff_fakes import FakeLlm


class Verdict(BaseModel):
    ok: bool
    note: str


def double(x: int) -> int:
    """Doubles x. A plain tool function, wrapped below."""
    return x * 2


def _user_turn(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=text)])


def _text_parts(events: list[Event]) -> list[str]:
    return [
        part.text
        for event in events
        for part in ((event.content.parts or []) if event.content else [])
        if part.text
    ]


async def _run(agent: LlmAgent, *, app_name: str = "t") -> tuple[list[Event], dict[str, Any]]:
    """Runs `agent` once through `InMemoryRunner` and returns (events, final_state)."""
    runner = InMemoryRunner(agent=agent, app_name=app_name)
    session = await runner.session_service.create_session(app_name=app_name, user_id="u1")
    events = [
        event
        async for event in runner.run_async(
            user_id="u1", session_id=session.id, new_message=_user_turn("go")
        )
    ]
    final = await runner.session_service.get_session(
        app_name=app_name, user_id="u1", session_id=session.id
    )
    assert final is not None, "session vanished between create and get"
    return events, dict(final.state)


# --------------------------------------------------------------------------- #
# DoD 2: a scripted LlmAgent run through InMemoryRunner returns the scripted response.
# --------------------------------------------------------------------------- #


async def test_scripted_text_response_is_returned() -> None:
    fake = FakeLlm.script(["the answer is 42"])
    agent = LlmAgent(name="t", model=fake)

    events, _ = await _run(agent)

    assert "the answer is 42" in _text_parts(events)


# --------------------------------------------------------------------------- #
# DoD 3: a BaseModel in the script round-trips through output_schema.
# --------------------------------------------------------------------------- #


async def test_basemodel_round_trips_through_output_schema() -> None:
    fake = FakeLlm.script([Verdict(ok=True, note="looks good")])
    agent = LlmAgent(name="t", model=fake, output_schema=Verdict, output_key="verdict")

    _, state = await _run(agent)

    assert state["verdict"] == {"ok": True, "note": "looks good"}


async def test_multiple_basemodels_yielded_in_script_order() -> None:
    fake = FakeLlm.script([Verdict(ok=True, note="first"), Verdict(ok=False, note="second")])
    agent = LlmAgent(name="t", model=fake, output_schema=Verdict, output_key="verdict")

    # Two independent turns against the same fake, in two separate sessions — each should
    # get the next scripted item, in order.
    _, state_one = await _run(agent, app_name="turn-one")
    _, state_two = await _run(agent, app_name="turn-two")

    assert state_one["verdict"] == {"ok": True, "note": "first"}
    assert state_two["verdict"] == {"ok": False, "note": "second"}


async def test_llmresponse_item_passes_through_untouched() -> None:
    canned = LlmResponse(content=types.Content(role="model", parts=[types.Part(text="verbatim")]))
    fake = FakeLlm.script([canned])
    agent = LlmAgent(name="t", model=fake)

    events, _ = await _run(agent)

    assert "verbatim" in _text_parts(events)


# --------------------------------------------------------------------------- #
# DoD 4: requests records tool declarations.
# --------------------------------------------------------------------------- #


async def test_records_requests_including_a_real_tool_declaration() -> None:
    fake = FakeLlm.script(["ok"])
    agent = LlmAgent(name="t", model=fake, tools=[FunctionTool(double)])

    await _run(agent)

    assert len(fake.requests) == 1
    request = fake.requests[0]
    assert isinstance(request, LlmRequest)
    assert "double" in request.tools_dict


async def test_requests_records_every_call_in_order() -> None:
    fake = FakeLlm.script(["first", "second"])
    agent = LlmAgent(name="t", model=fake)

    await _run(agent, app_name="a")
    await _run(agent, app_name="b")

    assert len(fake.requests) == 2


# --------------------------------------------------------------------------- #
# DoD 5: error= raises from the run, and the exception reaches the caller.
# --------------------------------------------------------------------------- #


async def test_error_reaches_the_caller_on_the_first_call() -> None:
    boom = ValueError("simulated model failure")
    fake = FakeLlm.script([], error=boom)
    agent = LlmAgent(name="t", model=fake)

    with pytest.raises(ValueError) as excinfo:
        await _run(agent)
    assert excinfo.value is boom


async def test_error_raises_only_after_scripted_responses_are_consumed() -> None:
    boom = RuntimeError("fails on the second call")
    fake = FakeLlm.script(["first turn is fine"], error=boom)
    agent = LlmAgent(name="t", model=fake)

    # First call succeeds and consumes the one scripted response.
    await _run(agent, app_name="first")
    # A second, independent call reaches the exhausted script and raises `error`.
    with pytest.raises(RuntimeError) as excinfo:
        await _run(agent, app_name="second")
    assert excinfo.value is boom


# --------------------------------------------------------------------------- #
# DoD 6: scripts shorter than the number of turns fail with a clear message.
# --------------------------------------------------------------------------- #


async def test_exhausted_script_raises_clear_message_not_bare_indexerror() -> None:
    fake = FakeLlm.script(["only one"])
    agent = LlmAgent(name="t", model=fake)

    await _run(agent, app_name="first")
    with pytest.raises(RuntimeError, match="script exhausted") as excinfo:
        await _run(agent, app_name="second")

    # It names the call count, not a bare "list index out of range" — a retry test that
    # silently reused the last response would tell a very different, wrong story here.
    assert "1 response" in str(excinfo.value)
    assert "call 2" in str(excinfo.value)
    assert not isinstance(excinfo.value, IndexError)


async def test_default_script_with_no_responses_raises_immediately() -> None:
    fake = FakeLlm.script()
    agent = LlmAgent(name="t", model=fake)

    with pytest.raises(RuntimeError, match="script exhausted"):
        await _run(agent)


# --------------------------------------------------------------------------- #
# DoD 7: mff_fakes imports google.adk and nothing else beyond contracts/pydantic.
# --------------------------------------------------------------------------- #

_ALLOWED_TOP_LEVEL_IMPORTS = {
    "__future__",
    "collections",
    "typing",
    "google",
    "pydantic",
    "mff_contracts",
    "mff_fakes",
}


def _top_level_imports(source: Path) -> set[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_package_imports_only_google_adk_and_contracts() -> None:
    src_root = Path(__file__).resolve().parents[1] / "src" / "mff_fakes"
    py_files = sorted(src_root.rglob("*.py"))
    assert py_files, "expected mff_fakes source files to exist"

    offenders: dict[str, set[str]] = {}
    for path in py_files:
        extra = _top_level_imports(path) - _ALLOWED_TOP_LEVEL_IMPORTS
        if extra:
            offenders[str(path)] = extra

    assert not offenders, f"mff_fakes imports outside google/pydantic/contracts: {offenders}"


def test_package_does_not_import_other_model_libraries() -> None:
    src_root = Path(__file__).resolve().parents[1] / "src" / "mff_fakes"
    banned = {"anthropic", "openai", "vertexai", "litellm", "pydantic_ai"}
    for path in sorted(src_root.rglob("*.py")):
        found = _top_level_imports(path)
        assert not (found & banned), f"{path} imports a banned model library: {found & banned}"
