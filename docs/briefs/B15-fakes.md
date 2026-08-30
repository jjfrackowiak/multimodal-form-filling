# B15 · `FakeLlm` — the ADK test double

**Branch:** `feat/fakes` → PR into `main`
**Depends on:** B0 (merged).
**Needs:** nothing. No key, no network, ever.

**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## Why this branch exists

Pydantic AI shipped `TestModel` and `FunctionModel` as public API. **ADK ships no
supported equivalent** — it has a `MockModel` in its own `tests/unittests/testing_utils.py`,
which is not public API and must not be imported. So we own one.

It is its own PR, ahead of Layer 1, for one reason: **B2, B6, B7 and B8 all need it.** Four
private copies of the same fake, drifting apart over four PRs, is exactly what the
disjoint-ownership table exists to prevent. Sixty lines merged once is cheaper than that.

## What you are building

`packages/mff-fakes` — one class, one test file.

```python
class FakeLlm(BaseLlm):
    """A BaseLlm that returns scripted responses and records what it was asked."""

    @classmethod
    def script(cls, responses: Sequence[str | BaseModel | LlmResponse]) -> FakeLlm: ...

    requests: list[LlmRequest]        # every request, in order, for assertion
    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]: ...
```

Three things it must do, because three branches depend on each:

1. **Yield scripted responses in order.** A `BaseModel` in the script is serialised to the
   JSON an `output_schema` run would produce, so a test can write
   `FakeLlm.script([SliceReport(...)])` instead of hand-writing JSON.
2. **Record every `LlmRequest`.** B8 has to assert that an agent carrying both
   `output_schema` and `tools` still has its real tools in the request — that assertion is
   only possible against a recorded request.
3. **Raise on demand.** An `error=` argument, so the run loop's error boundary can be
   tested without a network.

## How it is wired in

ADK's `LlmAgent.canonical_model` returns a `BaseLlm` instance as-is, so no `LLMRegistry`
registration is needed:

```python
agent = LlmAgent(name="t", model=FakeLlm.script([...]), output_schema=SliceReport)
```

That is the whole integration. Keep it that way — if a consumer needs a registry entry or a
model-name regex, the fake has grown a second job.

## Also in this PR

`mff_fakes` has to be added to two places in the root `pyproject.toml`, which is why this
cannot be folded into a branch that owns neither:

- `[tool.ruff.lint.isort] known-first-party`
- `[tool.importlinter] root_packages`

Place it in the layer contract alongside the other packages (`services → packages →
mff-contracts`). It depends on `google-adk` and `mff-contracts` and nothing else.

**It is a `dev` dependency of its consumers, never a runtime one.** No service image
contains `mff-fakes`.

## What to test against

Your own package only. Do not reach for the fleet fixture — the branches that consume you
do that, and a fake with fixture knowledge baked in is a fake with opinions.

## Definition of done

1. `make check` green, coverage ≥ 85%.
2. A scripted `LlmAgent` run through `InMemoryRunner` returns the scripted response.
3. A `BaseModel` in the script round-trips: agent with `output_schema=X` yields a valid `X`.
4. `requests` records tool declarations — assert a tool passed in `tools=[…]` appears in the
   recorded `LlmRequest`. This is the assertion B8's most important test is built on.
5. `error=` raises from the run, and the exception reaches the caller.
6. Scripts shorter than the number of turns fail with a clear message, not `IndexError` —
   a retry test that silently reuses the last response tests nothing.
7. An import test: `mff_fakes` imports `google.adk` and nothing else beyond contracts.

## Out of scope

Prompts, agents, flows, the retry loop (B8), anything fixture-shaped, and any attempt to
make this a general-purpose mocking library. One class, three behaviours.
