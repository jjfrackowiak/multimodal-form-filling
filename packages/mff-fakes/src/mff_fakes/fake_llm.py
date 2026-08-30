"""`FakeLlm` — the ADK test double.

Pydantic AI shipped `TestModel` and `FunctionModel` as public API. ADK ships no supported
equivalent — it has a `MockModel` in its own `tests/unittests/testing_utils.py`, which is
not public API and must not be imported. `FakeLlm` is what every model-touching branch in
this repository uses instead.

## What it is, and is not

`FakeLlm` is a `BaseLlm` that returns exactly what it was told to return, in the order it
was told, and nothing else. It never reads the prompt, never inspects the tools it was
given, never has an opinion about whether a request makes sense. That is deliberate and it
is the same trade-off `InventoryVisionTool` makes for image understanding (see
`mff_vision.mock`): a fake that echoes a script **cannot be wrong**, which is exactly what
makes it useless for judging response quality and ideal for everything else — an agent
wired to it is fully deterministic, so a failing test means the agent's wiring is broken,
never that a model had an off day.

The corollary is the trap: a `FakeLlm.script([...])` test proves an agent can *consume* a
well-formed response. It proves nothing about whether the agent's prompt would ever cause a
real model to *produce* one. Keep that distinction in view when a test built on this class
starts to feel like a substitute for a live eval — it is not one, and is not meant to be.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel, Field, PrivateAttr

__all__ = ["FakeLlm"]

# A scripted turn: raw text returned verbatim, a pydantic model serialised to the JSON an
# `output_schema` run would produce, or a fully-formed `LlmResponse` for a test that needs
# control over fields `FakeLlm` would not otherwise set (e.g. `usage_metadata`).
ScriptedResponse = str | BaseModel | LlmResponse


class FakeLlm(BaseLlm):
    """A `BaseLlm` that returns scripted responses and records what it was asked.

    Construct with `FakeLlm.script(...)`, then pass the instance straight into
    `LlmAgent(model=...)`. ADK's `LlmAgent.canonical_model` returns a `BaseLlm` instance
    as-is, so no `LLMRegistry` entry or model-name regex is needed — that is the whole
    integration, and it is meant to stay that way. If a consumer needs more than that, the
    fake has grown a second job.
    """

    model: str = "fake-llm"

    #: Every `LlmRequest` this instance has been asked to answer, in call order — so a test
    #: can assert what an agent actually sent, e.g. that its real tools survived alongside
    #: an `output_schema`. Public and mutable so a caller can also just read the length.
    requests: list[LlmRequest] = Field(default_factory=list)

    _script: list[ScriptedResponse] = PrivateAttr(default_factory=list)
    _error: BaseException | None = PrivateAttr(default=None)
    _calls: int = PrivateAttr(default=0)

    @classmethod
    def script(
        cls,
        responses: Sequence[ScriptedResponse] = (),
        *,
        error: BaseException | None = None,
    ) -> FakeLlm:
        """Build a `FakeLlm` that yields `responses` in order, one per call.

        A `str` is wrapped as model text. A `BaseModel` is serialised with
        `model_dump_json()` — the JSON an `output_schema` run would produce — so a test can
        write `FakeLlm.script([SliceReport(...)])` instead of hand-writing JSON. An
        `LlmResponse` is passed through untouched.

        `error`, if given, is raised once `responses` is exhausted, in place of the
        "script exhausted" error below — the run loop's error boundary can then be
        exercised without a network. Pass `responses=()` to raise on the very first call.
        """
        instance = cls()
        instance._script = list(responses)
        instance._error = error
        return instance

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        if self._calls >= len(self._script):
            if self._error is not None:
                raise self._error
            raise RuntimeError(
                f"FakeLlm script exhausted: {len(self._script)} response(s) scripted, "
                f"but this is call {self._calls + 1}. Script more responses, or pass "
                "error= if the run is expected to fail at this point."
            )
        item = self._script[self._calls]
        self._calls += 1
        yield _as_llm_response(item)


def _as_llm_response(item: ScriptedResponse) -> LlmResponse:
    if isinstance(item, LlmResponse):
        return item
    text = item.model_dump_json() if isinstance(item, BaseModel) else item
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))
