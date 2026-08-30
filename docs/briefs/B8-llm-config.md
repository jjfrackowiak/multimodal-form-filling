# B8 · Model wiring and settings

**Branch:** `feat/llm-config` → PR into `main`
**Depends on:** B0 (merged).
**Needs:** `GOOGLE_API_KEY` for the one live smoke test. Everything else runs on
`TestModel`.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`services/editor-service/src/**/llm/**` and `settings.py` — **the only place in the repo
that constructs a model client.** One factory both flows call, plus the editor service's
HTTP surface.

```python
def build_agent(*, output_type: type[T], instructions: str,
                toolsets: list[AbstractToolset]) -> Agent[EditorDeps, T]: ...
```

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

## Use `pydantic-ai-slim`, never `pydantic-ai`

The meta-package resolves to:

```
pydantic-ai-slim[openai,anthropic,google,cli,mcp,evals,web,retries,logfire]
```

which ships the **OpenAI and Anthropic SDKs**, an MCP client and a CLI into every image so
we can talk to Gemini. Depend on:

```toml
dependencies = ["pydantic-ai-slim[google,evals]", "mff-contracts", "mff-vision"]
```

`[google]` brings `google-genai`, which is where `HttpRetryOptions` lives — transport retry
needs no further extra. The separate `[retries]` extra is for Pydantic AI's own tenacity
transport; add it only if you adopt that. `[logfire]` stays out by default: observability
should be a per-environment opt-in, not weight in every image.

**`python-docx` must not appear here.** The orchestrator parses documents into `Node`s and
hands them over as data. If you find yourself needing it, something has moved to the wrong
service.

## The wiring

```python
GoogleModel(settings.model_id, provider=GoogleProvider(api_key=settings.google_api_key,
                                                       retry_options=HttpRetryOptions(...)))
```

**Pin the model id explicitly in settings**, never an alias. An upstream default change
would silently move every eval baseline.

`UsageLimits` per slice run. Shared `RunUsage` so a job's cost is attributable. **There is
no per-job ceiling yet — that is D5, deferred** — but structure the accounting so adding
one later is a change in one place.

## The retry loop lives here

This is the consequence of the design that most affects your code. The editor owns the
whole retry lifecycle:

1. Run the agent.
2. Validate completeness **on Python objects** — every requirement answered, justified,
   anchor resolves. Deterministic code, not the model judging itself.
3. On failure raise `ModelRetry`; the agent retries with its own previous output and the
   error, via `message_history`.
4. After **three attempts**, mark the stragglers `unverified` and return **normally**.

`UnexpectedModelBehavior` must never escape to the orchestrator. It expects a
`SliceReport` that is **always well-formed** — complete, or complete-with-`unverified`.
That is why `SliceRequest` carries no `pending`, no `history` and no `validator_error`.

Set `attempts_used` on the report. A slice routinely needing three tries is a prompt
problem, and it should be visible without reading logs.

## Definition of done

1. `make check` green, coverage ≥ 85%.
2. **Every test uses `TestModel` or `FunctionModel`. No network in CI.**
3. A dependency test asserting `openai` and `anthropic` are **not** importable in this
   service's environment — prove the slim install worked rather than assuming.
4. The retry lifecycle tested with `FunctionModel`: force validation failure three times,
   assert a well-formed report comes back with those requirements `unverified` and
   `attempts_used == 3`, and that **nothing raises**.
5. `attempts_used == 1` on a clean run.
6. `POST /slices:run` round-trips a real `SliceRequest` from the fixture.
7. `/healthz` does not construct a model client — a health check must not cost a token or
   fail on a bad key.
8. One live Gemini smoke test behind an env flag, run manually, never in CI.

## Out of scope

Prompts and agent instructions (B6/B7), the orchestrator (B5), documents (B1), Dockerfiles
(B10).
