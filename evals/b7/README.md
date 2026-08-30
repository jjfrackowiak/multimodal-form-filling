# B7 live net-new evaluation

This is a manually invoked Tier B evaluation of `compose_netnew` with its real default
Gemini model. It is not collected by pytest and never uses `FakeLlm` or an LLM judge.

Run it only after authenticating ADC:

```bash
MFF_B7_LIVE_EVAL=1 GOOGLE_CLOUD_PROJECT=<project> uv run python evals/b7/run.py
```

The evaluator loads the fleet fixture's labelled inventory and client text inputs, calls
`compose_netnew(..., model=None)`, then scores the returned report and mutated draft
against `cases.yaml` and `structure.yaml`. It enforces the E2 130-second ceiling with
Pydantic Evals `MaxDuration`, requires R-01 and R-04 to be `shortfall`, all other
requirements to be `realised`, and checks settled requirements, entry anchors, real
`DraftOp`s, applier acceptance, and a compilable net-new draft.

The run report includes the resolved model identifier in its output; no credentials are
read or printed by this evaluator. The current B7 public flow does not expose per-run
input/output token usage to an external evaluator, so this runner does not fabricate it.