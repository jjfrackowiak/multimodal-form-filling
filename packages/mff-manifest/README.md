# mff-manifest

Free text into `Requirement[]` (req 5). Req 5 calls this "a simple parsing /
normalisation step"; `fixtures/fleet-vehicle-return/manifest.txt` — ten lines of real,
misspelled Polish — is the proof it is not.

## The one entry point

```python
class RequirementExtractor(Protocol):
    """Implemented in the editor service, which owns all model access."""
    async def extract(self, chunk: str, *, offset: int) -> list[Requirement]: ...


async def parse_manifest(raw: str, *, extractor: RequirementExtractor) -> Manifest: ...
```

**This package imports no agent framework and no model library** — not `google.adk`, not
`google.genai`, not anything else a real extractor would need. It depends on the
`RequirementExtractor` Protocol; the implementation is the editor service's job. Proven,
not just documented, by `tests/test_import_boundary.py` (parses every source file's AST
without executing it, and separately checks a fresh interpreter's `sys.modules` after
`import mff_manifest`) and by the workspace `import-linter` contract.

## Two stages

1. **`presplit`** — deterministic. Splits `raw` on blank lines into paragraph-shaped
   chunks, each carrying its own character offset into `raw`. Cheap, reproducible, no
   model output anywhere in its path. `fleet-vehicle-return/manifest.txt` has no blank
   lines, so it pre-splits to exactly one chunk — the whole manifest goes to the model in
   one call, which is what makes the constraint on line 10 (`Podsufitka trzeba spomiędzy
   forteli zrobić`) linkable back to the item it qualifies on line 4, six lines away. A
   line-at-a-time splitter can never let a model make that link.
2. **`extractor.extract`** — one small model call per chunk, behind
   `RequirementExtractor`. Does the one thing a splitter cannot: decide how many discrete,
   individually-checkable requirements a chunk names (a count like `4x fotele` is **one**
   requirement with `expected_count: 4`, never four), link a stranded constraint back to
   its subject, and surface a genuine ambiguity (`Pod maską`, appearing on both line 2 and
   line 5) rather than silently resolving it.

`parse_manifest` never trusts what the extractor says about `ordinal`, `source_line` or
`id` — those are **recomputed** from `source_span` against `raw` after every chunk
returns. That is what makes the provenance invariant hold regardless of what the model
does: every `source_span` is verbatim in `raw`, and `ordinal == raw.index(source_span)`.
Ids are assigned only after every chunk's results are collected, sorted by
`(ordinal, text)`, and numbered `R-01…R-10` — `text` is the tiebreak for the fixture's two
colliding pairs (R-05/R-06, R-08/R-09), which share both offset and span.

## Validation instead of `ModelRetry`

ADK ships no `output_validator`/`ModelRetry` pair. The equivalent here is explicit: a
`source_span` (a requirement's or its constraint's) that is not a verbatim substring of
`raw` is a hard structural failure. `parse_manifest` re-asks the extractor — appending a
note naming the offending span — up to `DEFAULT_MAX_ATTEMPTS` (3) times, then raises
`ManifestParseError`. The caller always gets a well-formed `Manifest` or a raised error,
never a silently truncated requirement list.

## Recall ≥ 0.95, precision 1.0

Missing a requirement is recoverable — the client sees the confirmation list and says so.
Inventing one means telling the client their document fails a rule they never wrote. This
package never invents; the extractor behind the Protocol is where that discipline actually
has to hold, which is what the live eval below measures.

## Tests

Every unit test injects a local, in-process double (`tests/fakes.py::ScriptedExtractor`)
through the `RequirementExtractor` Protocol — no network, no model library, ever, in a
normal `make check` run. It is deliberately **not** `FakeLlm` from `mff-fakes`: that class
wraps ADK's `BaseLlm`, which is exactly the import this package's tests also prove absent.

- `tests/golden.py` — the golden parse of the fixture, as `mff_contracts.Requirement`
  objects, mirroring `expected_requirements.yaml` by hand.
- `test_golden_fixture.py` — all 10 requirements, field by field, against the golden data.
- `test_invariants.py` — the provenance invariant, asserted as a hard failure, plus that a
  bad span never comes back as a silently truncated list.
- `test_retry.py` — recovery on a later attempt, the attempt cap, and that a script
  shorter than the attempts needed fails loudly rather than with a bare `IndexError`.
- `test_ids_and_ordering.py` — the `(ordinal, text)` tiebreak, tested directly on both
  colliding pairs by feeding them to the parser in the wrong order.
- `test_adversarial.py` — D4 (prompt-injection resistance) is deferred, but the test lives
  here now; today it proves the plumbing carries no text-sniffing logic of its own.
- `test_import_boundary.py` — the Protocol boundary, proven rather than assumed.

## Live eval

Gated behind `MFF_MANIFEST_LIVE_EVAL=1`, never run in CI. `tests/live_extractor.py`
(imported only from inside the gated test) is a minimal, real `RequirementExtractor` —
not the production implementation, which lives in the editor service — that prompts
`PARSER_MODEL_ID` (`gemma-3-27b-it` by default, see `.env.example`) for JSON and parses
the result, because Gemma has no native structured-output mode. It needs the package's
`live-eval` extra:

```bash
uv sync --extra live-eval
MFF_MANIFEST_LIVE_EVAL=1 GOOGLE_API_KEY=... \
    uv run pytest packages/mff-manifest/tests/test_live_eval.py -s
```

Scoring is structural (`SpanRecallPrecision` in `test_live_eval.py`), never an LLM judge:
requirements are matched to `golden.GOLDEN_REQUIREMENTS` by verbatim `source_span`
overlap, with a per-span count comparison so that an over-split `4x fotele` costs
precision rather than passing for free. `test_env_flag_skips_cleanly_without_a_live_call`
is the one assertion this file makes in a normal `make check` run: without the flag, the
module never imports `google.genai` at all.

### Baseline

**Not filled in.** In this environment `GOOGLE_API_KEY` returns
`HTTP 403 API_KEY_SERVICE_BLOCKED`, so the live path cannot run here — verified: with the
flag set and that key, `test_live_eval_against_fleet_vehicle_return` catches the failure
and skips cleanly rather than failing the suite, exactly as designed. Run it manually with
a working key and record the real numbers below rather than trusting these to be
accurate:

| date | model_id | recall | precision | p95 latency | tokens (last run) |
|---|---|---|---|---|---|
| _unfilled_ | `gemma-3-27b-it` | — | — | — | — |

## What is genuinely ambiguous here

`golden.py`'s `GOLDEN_REQUIREMENTS` resolves R-01 (`Pod maską`, lines 2 and 5) to
`expected_count: 2`, on the strength of the client's own stated total (16 photos, line 1)
— not because a repeated mention is obviously two photographs rather than one restated.
That is a real judgement call baked into the golden fixture, not a fact this package
derives; `test_ambiguity_is_recorded_not_resolved_away` only checks that the *ambiguity is
recorded*, not that this particular resolution is the only defensible one. A parser that
instead resolved to `expected_count: 1` (15 photos total, disagreeing with the client's
own count) would be making the opposite defensible call and would fail this package's
golden test — worth knowing if a future brief revisits the fixture.
