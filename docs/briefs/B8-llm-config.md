# B8 · Model wiring and settings

**Branch:** `feat/llm-config` → PR into `main`
**Depends on:** B0 (merged), B15 (`mff-fakes`).
**Needs:** `GOOGLE_API_KEY` for the one live smoke test. Everything else runs on
`FakeLlm`.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`services/editor-service/src/**/llm/**` and `settings.py` — **the only place in the repo
that constructs a model client.** One agent factory and one run loop that both flows call,
plus the editor service's HTTP surface.

```python
def build_agent(
    *,
    name: str,
    output_schema: type[BaseModel],
    instruction: str,
    tools: list[Callable[..., Any]],
) -> LlmAgent: ...


async def run_slice(req: SliceRequest, deps: EditorDeps) -> SliceReport: ...
```

`output_schema` is a plain pydantic model from `mff-contracts`. **Pydantic is not going
anywhere** — ADK replaces the agent runtime, not the type system. Every tool signature,
every structured output and every validator in this service stays a pydantic model.

Plus the worker endpoint:

```
POST /slices:run    SliceRequest → SliceReport
GET  /healthz
```

## Requirements you own

None of the 17 directly. You own the substrate reqs 11–17 execute on, and the placement
rule that keeps model access in one service.

## Directories you own

```
services/editor-service/src/**/llm/**
services/editor-service/src/**/settings.py
services/editor-service/src/**/main.py
services/editor-service/src/**/api/**
services/editor-service/tests/llm/**
```

`flows/` and `agents/` are B6's and B7's — you provide what they call.

## Use bare `google-adk` — no extras

The base install is 25 packages and carries `google-genai`, which is all we need. The
weight is in the extras, and two of them ship the very SDKs the old plan fought to keep
out: **`google-adk[extensions]` and `google-adk[all]` both contain `anthropic` and
`openai`.** `[eval]` drags in pandas, pyarrow, nltk and `google-cloud-aiplatform`; `[gcp]`
is B12's business, not yours; `[db]` is only for ADK's `DatabaseSessionService`, which we
do not use.

```toml
dependencies = ["google-adk>=2.8", "mff-contracts", "mff-vision"]
```

`types.HttpRetryOptions` lives in `google-genai`, which arrives with the base install, so
transport retry needs no extra. **`pydantic-evals` goes in the `dev` group, never here** —
it pins `pydantic-ai-slim`, which must not reach a service image. Observability stays
opt-in: ADK carries the OTel API and SDK in its base, but the GCP exporters are in `[gcp]`
and stay out until someone is actually collecting.

**`python-docx` must not appear here.** The orchestrator parses documents into `Node`s and
hands them over as data. If you find yourself needing it, something has moved to the wrong
service.

## The wiring

```python
from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

model = Gemini(
    model=settings.model_id,
    retry_options=types.HttpRetryOptions(attempts=3),
)
```

**Pin the model id explicitly in settings**, never an alias. An upstream default change
would silently move every eval baseline — and under ADK it now moves a *capability* too:
whether the model can serve `output_schema` and `tools` in one request is read off
`canonical_model.capabilities.output_schema_and_tools`.

**Structured output and tools together.** Both flows need it — derivative emits
`ReviewComment[]` while calling the vision tool, net-new emits a report while calling
`set`/`append`/`delete`. Set `output_schema` and `tools` on the same `LlmAgent` and let ADK
sort it out: where the model supports both, the schema goes onto the request; where it does
not, `_OutputSchemaRequestProcessor` injects a `set_model_response` tool carrying the schema
and **leaves your real tools in place**. Do not hand-roll a formatter sub-agent, and do not
split the agent in two.

**Usage accounting is a plugin.** ADK has no `UsageLimits`. Write a `UsagePlugin(BasePlugin)`
registered on the `App`, summing `llm_response.usage_metadata` in `after_model_callback` and
refusing the call in `before_model_callback` once the slice budget is spent (return an
`LlmResponse` to short-circuit). **There is no per-job ceiling yet — that is D5, deferred** —
but keep the accounting in the plugin so adding one later is a change in one place.

**Sessions are ours, in memory, per slice.** Use `InMemorySessionService`. Do **not** reach
for `DatabaseSessionService` or ADK's `ArtifactService`: B12 owns job persistence, and two
persistence layers is one too many. The session exists only for the life of a slice run —
it is the retry history, nothing more.

## The retry loop lives here

This is the consequence of the design that most affects your code, and it is the piece ADK
does *not* hand you. There is no `ModelRetry`; you write the loop. That is a feature — the
plan's two retry rules were always more than `ModelRetry` did on its own.

1. Create one session for the slice.
2. Run a turn.
3. Validate completeness **on Python objects** — every requirement answered, justified,
   anchor resolves. Deterministic code, not the model judging itself.
4. On failure, append the validator's error to the **same session** as the next user turn
   and go again. ADK accumulates the events, so the agent sees its own previous output and
   what was wrong with it; you never build a message history by hand.
5. After **three attempts**, mark the stragglers `unverified` and return **normally**.

```python
async def run_slice(req: SliceRequest, deps: EditorDeps) -> SliceReport:
    session = await session_service.create_session(
        app_name=APP, user_id=req.job_id, session_id=req.slice_id,
        state={"slice_id": req.slice_id, "form_id": req.form_id},
    )
    settled: dict[str, ReviewComment] = {}
    pending = list(req.requirement_ids)
    message = initial_prompt(req)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        output = await _one_turn(session, message, deps)
        passed, errors = validate(output, pending)      # deterministic, per requirement
        settled.update(passed)                          # rule 2: never revisited
        pending = [r for r in pending if r not in settled]
        if not pending:
            break
        message = retry_prompt(pending, errors)         # rule 1: same session, next turn

    return SliceReport(
        comments=list(settled.values()),
        unverified=pending,
        attempts_used=attempt,
        ops=deps.op_log,
    )
```

Note that **rule 2 — a settled answer is never revisited — falls out of `pending` narrowing
on each pass**, and that it was never something `ModelRetry` gave us. Writing the loop by
hand costs about fifteen lines and makes both rules visible in one place.

**No ADK or provider exception may escape to the orchestrator.** It expects a `SliceReport`
that is **always well-formed** — complete, or complete-with-`unverified`. Catch at the run
boundary and convert. That is why `SliceRequest` carries no `pending`, no `history` and no
`validator_error`.

## Where the artifact lives — read this before writing a tool

ADK's `session.state` is a JSON-shaped dict committed as a `state_delta` on **every event**.
The `Artifact` is a large, live, line-addressable Python object that tools mutate between
model calls. Putting it in `session.state` would serialise the whole document on every tool
call, which is the opposite of what req 12 asks for.

- The `Artifact` lives in `EditorDeps`, held by `run_slice` for the life of the slice.
- Mutation tools come from a **factory that closes over that `EditorDeps`**. They mutate in
  place and append a `DraftOp` to the log.
- A tool that needs framework context takes a `tool_context: ToolContext` parameter — ADK
  injects it and hides it from the model's view of the signature.
- `session.state` carries **only scalars the instruction template interpolates**:
  `slice_id`, `form_id`, requirement count.

Set `attempts_used` on the report. A slice routinely needing three tries is a prompt
problem, and it should be visible without reading logs.

## What to test against

- **`fixtures/fleet-vehicle-return/expected_requirements.yaml`** — build a real `SliceRequest` from the first six
  requirements rather than inventing one.
- **`fixtures/fleet-vehicle-return/expected_output/review.yaml`** — what a `FakeLlm` should
  return, so the retry lifecycle is exercised on realistic comments.

## Definition of done

1. `make check` green, coverage ≥ 85%.
2. **Every test uses `FakeLlm` from `mff-fakes`. No network in CI.**
3. A dependency test asserting `openai` and `anthropic` are **not** importable in this
   service's environment — prove the bare install worked rather than assuming. This test
   predates the move to ADK and is kept verbatim: it was written against
   `pydantic-ai`'s meta-package and catches `google-adk[extensions]`/`[all]` unchanged.
4. The retry lifecycle tested with `FakeLlm`: force validation failure three times,
   assert a well-formed report comes back with those requirements `unverified` and
   `attempts_used == 3`, and that **nothing raises**.
5. `attempts_used == 1` on a clean run.
6. `POST /slices:run` round-trips a real `SliceRequest` from the fixture.
7. `/healthz` does not construct a model client — a health check must not cost a token or
   fail on a bad key.
8. A test that an `LlmAgent` carrying **both** `output_schema` and a non-empty `tools` list
   produces a request in which the real tools survive — assert against
   `FakeLlm.requests[-1]`. This is the one ADK behaviour the whole design rests on; prove
   it rather than trusting the release notes.
9. Rule 2 tested directly: a requirement that passes on attempt 1 and whose answer the
   model *changes* on attempt 2 must keep its attempt-1 verdict. `FakeLlm` makes this
   scriptable, and it is what keeps E1's exact-match assertion sound.
10. `UsagePlugin` totals asserted against a scripted `usage_metadata`, and a slice that
    exceeds its budget short-circuits in `before_model_callback` rather than calling out.
11. One live Gemini smoke test behind an env flag, run manually, never in CI.

## Out of scope

Prompts and agent instructions (B6/B7), the orchestrator (B5), documents (B1), Dockerfiles
(B10).
