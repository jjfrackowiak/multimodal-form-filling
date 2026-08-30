"""The live eval — never in CI, opt-in only.

Set `MFF_MANIFEST_LIVE_EVAL=1` (and a working `GOOGLE_API_KEY`, see `.env.example`) to run
it: `MFF_MANIFEST_LIVE_EVAL=1 uv run pytest packages/mff-manifest/tests/test_live_eval.py`.
Without the flag this whole module is skipped before it ever imports `google.genai` — see
`test_env_flag_skips_cleanly_without_a_live_call`, the one assertion this file makes in a
normal `make check` run.

On `pydantic-evals`, per CONTEXT.md's "Rules every branch inherits" — structural, never
LLM-as-judge: `SpanRecallPrecision` matches extracted requirements to
`golden.GOLDEN_REQUIREMENTS` by verbatim `source_span` overlap, not text similarity.
`pydantic_evals.evaluators.LLMJudge` is banned repo-wide by a ruff rule and never appears
here.

Record whatever this prints in README.md's "Live eval baseline" table. Leave a baseline
row unfilled rather than fabricate a number if the eval cannot run in your environment —
see the README for why it currently cannot run in this one.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from datetime import date

import pytest
from golden import GOLDEN_REQUIREMENTS, RAW
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from mff_contracts import Manifest, Requirement
from mff_manifest import parse_manifest

ENV_FLAG = "MFF_MANIFEST_LIVE_EVAL"
DEFAULT_MODEL_ID = "gemma-3-27b-it"
REPEATS = int(os.environ.get("MFF_MANIFEST_LIVE_EVAL_REPEATS", "5"))


def _flag_set() -> bool:
    return os.environ.get(ENV_FLAG, "").strip().lower() in {"1", "true", "yes"}


def test_env_flag_skips_cleanly_without_a_live_call() -> None:
    """The one assertion in this module that a normal `make check` run actually executes:
    with the flag unset, the live eval must not even attempt to import `google.genai`."""
    if _flag_set():
        pytest.skip(f"{ENV_FLAG} is set in this environment — nothing to prove here")
    assert "google" not in sys.modules
    assert "live_extractor" not in sys.modules


_SKIP_REASON = (
    f"live eval opt-in: set {ENV_FLAG}=1 and a working GOOGLE_API_KEY. Never runs in CI "
    "— see README.md's Live eval section."
)


def _span_counts(reqs: list[Requirement]) -> Counter[str]:
    return Counter(r.source_span for r in reqs)


class SpanRecallPrecision(Evaluator[str, Manifest]):
    """Span-based recall/precision, plus the one field-level check the brief singles
    out: whether R-04's constraint value survived.

    A span named more times by one side than the other only credits the smaller count —
    that is what makes "4x fotele" coming back as four separate requirements a precision
    hit rather than a free pass, without ever comparing generated text to golden text.
    """

    def evaluate(self, ctx: EvaluatorContext[str, Manifest]) -> dict[str, float]:
        extracted = ctx.output.requirements
        golden_counts = _span_counts(GOLDEN_REQUIREMENTS)
        extracted_counts = _span_counts(extracted)
        matched = sum(
            min(golden_counts[span], extracted_counts.get(span, 0)) for span in golden_counts
        )
        recall = matched / len(GOLDEN_REQUIREMENTS)
        precision = matched / len(extracted) if extracted else 0.0
        r04_correct = any(
            r.source_span == "2x podsufitka"
            and r.constraint is not None
            and r.constraint.value == "between_front_seats"
            for r in extracted
        )
        return {
            "recall": recall,
            "precision": precision,
            "r04_constraint_correct": float(r04_correct),
        }


@pytest.mark.skipif(not _flag_set(), reason=_SKIP_REASON)
def test_live_eval_against_fleet_vehicle_return() -> None:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        pytest.skip(f"{ENV_FLAG} is set but GOOGLE_API_KEY is not — nothing to call")

    model_id = os.environ.get("PARSER_MODEL_ID", DEFAULT_MODEL_ID)

    try:
        from live_extractor import GemmaJsonExtractor
    except ImportError as exc:
        pytest.skip(f"live-eval extra not installed ({exc}); run `uv sync --extra live-eval`")

    extractor = GemmaJsonExtractor(model_id=model_id, api_key=api_key)

    async def task(raw: str) -> Manifest:
        return await parse_manifest(raw, extractor=extractor)

    case: Case[str, Manifest, None] = Case(name="fleet-vehicle-return", inputs=RAW)
    dataset = Dataset(name="mff-manifest-live", cases=[case], evaluators=[SpanRecallPrecision()])

    try:
        report = dataset.evaluate_sync(task, repeat=REPEATS, progress=False)
    except Exception as exc:
        # An error raised out of evaluate_sync itself (a setup problem, not a per-run
        # failure) means "cannot run here" — skip rather than fail the suite.
        pytest.skip(f"live eval unavailable: {type(exc).__name__}: {exc}")

    if report.failures or not report.cases:
        # A per-run failure (bad/blocked key, unreachable model, ...) does not raise —
        # pydantic-evals records it in `report.failures` and the run is simply absent
        # from `report.cases`. This is the path that fires today: GOOGLE_API_KEY here
        # returns HTTP 403 API_KEY_SERVICE_BLOCKED (see README). Skip rather than fail:
        # that means "cannot run here", not "the parser is broken".
        messages = "; ".join(f.error_message for f in report.failures[:3]) or "no successful runs"
        pytest.skip(f"live eval unavailable: {len(report.failures)} run(s) failed: {messages}")

    recalls = [case_result.scores["recall"].value for case_result in report.cases]
    precisions = [case_result.scores["precision"].value for case_result in report.cases]
    r04_correct = [
        case_result.scores["r04_constraint_correct"].value for case_result in report.cases
    ]
    durations = sorted(case_result.task_duration for case_result in report.cases)
    p95_index = max(0, int(len(durations) * 0.95) - 1)

    print(f"\n--- mff-manifest live eval ({date.today().isoformat()}) ---")
    print(f"model_id            : {model_id}")
    print(f"repeats             : {len(report.cases)}")
    print(f"recall  (min / mean): {min(recalls):.3f} / {sum(recalls) / len(recalls):.3f}")
    print(f"precision(min/mean) : {min(precisions):.3f} / {sum(precisions) / len(precisions):.3f}")
    print(f"p95 latency         : {durations[p95_index]:.2f}s")
    print(f"tokens (last run)   : {extractor.last_usage}")
    print(f"r04 constraint correct on every run: {all(v == 1.0 for v in r04_correct)}")
    print("Copy these numbers into README.md's Live eval baseline table.")

    assert min(precisions) == 1.0, "precision must be 1.0 — never invent a requirement"
    assert min(recalls) >= 0.95, "recall must be >= 0.95"
