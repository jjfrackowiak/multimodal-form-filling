# mff-fakes

`FakeLlm` — the ADK test double every model-touching branch (B2, B6, B7, B8) uses so CI
never makes a live model call.

## Why this exists

Pydantic AI shipped `TestModel` and `FunctionModel` as public API. ADK ships no supported
equivalent — it has a `MockModel` in its own `tests/unittests/testing_utils.py`, which is
not public API and must not be imported. Sixty lines merged once here is cheaper than four
branches each growing a private copy that drifts.

## Usage

```python
from google.adk.agents import LlmAgent
from mff_fakes import FakeLlm

agent = LlmAgent(name="t", model=FakeLlm.script([SliceReport(ok=True)]), output_schema=SliceReport)
```

That is the whole integration. ADK's `LlmAgent.canonical_model` returns a `BaseLlm`
instance as-is, so no `LLMRegistry` entry or model-name regex is needed. `FakeLlm` deliberately
stays a one-class, three-behaviour fake:

1. **Yields scripted responses in order.** A `str` becomes model text; a `pydantic.BaseModel`
   is serialised with `model_dump_json()` — the JSON an `output_schema` run would produce —
   so a test writes `FakeLlm.script([SliceReport(...)])` instead of hand-writing JSON; an
   `LlmResponse` passes through untouched for tests that need full control.
2. **Records every `LlmRequest`** it was asked to answer, in `self.requests`, in call
   order — so a test can assert an agent's real tools survived alongside an `output_schema`
   (`request.tools_dict`), which is the assertion B8's most important test is built on.
3. **Raises on demand.** `error=` is raised once the script is exhausted, so a run loop's
   error boundary can be exercised without a network. A script that runs out with no
   `error=` set raises a clear `RuntimeError` naming the call count — never a bare
   `IndexError` that a retry test could misread as reusing the last response.

## The trade-off, stated plainly

`FakeLlm` cannot be wrong: it echoes what it was told, never what a real model would say.
That is what makes an agent wired to it fully deterministic — a failing test means the
agent's wiring is broken, never that a model had an off day — and it is exactly why a test
built on this class proves an agent can *consume* a well-formed response, never that its
prompt would cause a real model to *produce* one. This is the same trade-off
`mff_vision.mock.InventoryVisionTool` makes for image understanding; both are meant for
structural, deterministic tests, and neither is a substitute for a live eval.

## What it is not

Not a general-purpose mocking library, not a registry, not a retry loop (that is B8's), and
it has no opinion about prompts, agents, or flows. `mff_fakes` is a **dev-group**
dependency of its consumers only — no service image ever contains it.
