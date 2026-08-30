"""The one live smoke test — brief DoD 12. Never in CI, opt-in only, on ADC with no key in
the environment: that is what proves the switch to Application Default Credentials
actually works, not just that the code compiles against it.

    MFF_EDITOR_LIVE_EVAL=1 GOOGLE_CLOUD_PROJECT=<your project> \\
        uv run pytest services/editor-service/tests/llm/test_live_smoke.py -v -s

Requires `gcloud auth application-default login` to have been run once on this machine
(see `.env.example`'s ADC section) — no `GOOGLE_API_KEY` anywhere, ever.

Hits both models this service knows about: `EDITOR_MODEL_ID` (`gemini-2.5-flash`) through
the exact `build_agent`/`run_slice` path this branch ships, and `PARSER_MODEL_ID`
(`gemma-4-26b-a4b-it-maas`) directly through `Gemini`, since the parser's own agent lives in
`mff_manifest` (B2), not here — this service only proves the model id and the `-maas`
serverless MaaS path answer at all.

`GOOGLE_CLOUD_LOCATION` must be `global` — verified live on 2026-08-30, both regional
(`us-central1`) endpoints 404 for these two model ids. See `.env.example`.
"""

from __future__ import annotations

import os

import pytest

ENV_FLAG = "MFF_EDITOR_LIVE_EVAL"


def _flag_set() -> bool:
    return os.environ.get(ENV_FLAG, "").strip().lower() in {"1", "true", "yes"}


def test_env_flag_is_unset_by_default() -> None:
    """The one assertion this module makes in a normal `make check` run: both live tests
    below carry `@pytest.mark.skipif(not _flag_set(), ...)`, so with the flag unset (the
    default — see `make check`'s own environment) they are skipped, not run. This is
    weaker than mff_manifest's equivalent check (which can assert `"google" not in
    sys.modules`): every other test module in this suite already imports `google.adk` via
    `FakeLlm`/`LlmAgent`, so that particular assertion does not hold here regardless of
    this module's own behaviour — the two `skipif` markers below are the real guarantee.
    """
    if _flag_set():
        pytest.skip(f"{ENV_FLAG} is set in this environment — nothing to prove here")


_SKIP_REASON = (
    f"live smoke test opt-in: set {ENV_FLAG}=1, GOOGLE_CLOUD_PROJECT, and run "
    "`gcloud auth application-default login` first. Never runs in CI."
)


@pytest.mark.skipif(not _flag_set(), reason=_SKIP_REASON)
async def test_editor_model_answers_with_schema_and_tool_via_build_agent() -> None:
    """`EDITOR_MODEL_ID` through the real `build_agent`/`run_slice` path: an
    ADC-authenticated Gemini call that carries both `output_schema` and a tool in one
    request — the behaviour `test_build_agent.py` proves against `FakeLlm`'s fallback path;
    this is the same behaviour against the real model, live."""
    from google.adk.agents import LlmAgent
    from google.adk.apps import App
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from pydantic import BaseModel

    from editor_service.llm.agent import build_agent
    from editor_service.settings import Settings

    settings = Settings.from_env()

    calls: list[str] = []

    def note_it(text: str) -> str:
        """Record a short note about the requirement."""
        calls.append(text)
        return "noted"

    class Verdict(BaseModel):
        note: str

    agent: LlmAgent = build_agent(
        name="live_smoke_reviewer",
        output_schema=Verdict,
        instruction=(
            "Call the note_it tool once with the word 'ok', then answer with the required "
            "JSON schema, setting note to the word 'done'."
        ),
        tools=[note_it],
        settings=settings,
    )

    assert agent.canonical_model.capabilities.output_schema_and_tools is True, (
        "expected gemini-2.5-flash to self-report output_schema_and_tools == True on "
        "Vertex — if this fails, the capability flag or the model id has changed and "
        "the fallback (set_model_response) path is now load-bearing for real traffic too"
    )

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="live_smoke_reviewer", user_id="u", session_id="s", state={}
    )
    runner = Runner(
        app=App(name="live_smoke_reviewer", root_agent=agent), session_service=session_service
    )

    final_event = None
    async for event in runner.run_async(
        user_id="u",
        session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text="Go.")]),
    ):
        final_event = event

    assert final_event is not None
    assert final_event.content is not None
    text = "".join(part.text or "" for part in final_event.content.parts or [])
    print(f"\n--- editor-service live smoke: {settings.editor_model_id} ---")
    print(f"tool called: {calls}")
    print(f"final text: {text}")

    parsed = Verdict.model_validate_json(text)
    assert parsed.note
    assert calls, "expected the model to call note_it at least once"


@pytest.mark.skipif(not _flag_set(), reason=_SKIP_REASON)
async def test_parser_model_answers_on_the_maas_path() -> None:
    """`PARSER_MODEL_ID` (`gemma-4-26b-a4b-it-maas`) — proves the model id and the `-maas`
    serverless path answer at all. The parser's own agent lives in B2 (`mff_manifest`), not
    here; this service only carries the settings value and is where the id was verified."""
    from google.adk.agents import LlmAgent
    from google.adk.apps import App
    from google.adk.models import Gemini
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from editor_service.settings import Settings

    settings = Settings.from_env()
    model = Gemini(model=settings.parser_model_id, retry_options=types.HttpRetryOptions(attempts=3))
    agent = LlmAgent(name="live_smoke_parser", model=model, instruction="Answer in one word.")

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="live_smoke_parser", user_id="u", session_id="s", state={}
    )
    runner = Runner(
        app=App(name="live_smoke_parser", root_agent=agent), session_service=session_service
    )

    final_event = None
    async for event in runner.run_async(
        user_id="u",
        session_id="s",
        new_message=types.Content(
            role="user", parts=[types.Part(text="Reply with exactly one word: hello")]
        ),
    ):
        final_event = event

    assert final_event is not None
    assert final_event.content is not None
    text = "".join(part.text or "" for part in final_event.content.parts or [])
    print(f"\n--- editor-service live smoke: {settings.parser_model_id} ---")
    print(f"final text: {text!r}")
    assert text.strip()
