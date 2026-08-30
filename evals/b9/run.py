"""Run the live B9 fleet workflow as a Pydantic Evals structural evaluation.

This Tier B evaluation is intentionally separate from pytest: it calls real Gemini through
Vertex AI ADC. Run `GOOGLE_CLOUD_PROJECT=<project> make eval` after authenticating with
`gcloud auth application-default login`.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, MaxDuration

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.e2e_demo import DemoRun, run_demo  # noqa: E402

from mff_contracts import Mode  # noqa: E402

_LIVE_EVAL_FLAG = "MFF_B9_LIVE_EVAL"
_CASES_PATH = Path(__file__).with_name("cases.yaml")


class FleetOutcome(BaseModel):
    """The small, serialisable outcome Pydantic Evals scores."""

    status: str
    attachments: int
    checker_passed: bool
    unverified: list[str]
    derivative_verdicts: dict[str, str]
    netnew_verdicts: dict[str, str]
    netnew_ops: int


class FleetStructuralEval(Evaluator[dict[str, Any], FleetOutcome]):
    """Score exact requirement outcomes without LLM-as-judge text similarity."""

    def evaluate(self, ctx: EvaluatorContext[dict[str, Any], FleetOutcome]) -> dict[str, float]:
        outcome = ctx.output
        expected_failures = frozenset(ctx.inputs["expected_failures"])
        requirement_ids = [f"R-{number:02d}" for number in range(1, 11)]
        expected_derivative = {
            requirement_id: ("fail" if requirement_id in expected_failures else "pass")
            for requirement_id in requirement_ids
        }
        expected_netnew = {
            requirement_id: ("shortfall" if requirement_id in expected_failures else "realised")
            for requirement_id in requirement_ids
        }
        return {
            "request_completed": float(outcome.status == "done"),
            "documents_delivered": float(outcome.attachments == 2),
            "golden_document_valid": float(outcome.checker_passed),
            "all_requirements_settled": float(not outcome.unverified),
            "derivative_verdicts": float(outcome.derivative_verdicts == expected_derivative),
            "netnew_verdicts": float(outcome.netnew_verdicts == expected_netnew),
            "netnew_authored_content": float(outcome.netnew_ops > 0),
        }


def _outcome(run: DemoRun) -> FleetOutcome:
    derivative: dict[str, str] = {}
    netnew: dict[str, str] = {}
    unverified: list[str] = []
    netnew_ops = 0
    reports_by_mode: dict[Mode, list[Any]] = defaultdict(list)

    for request, report in run.flow_runs:
        reports_by_mode[request.mode].append(report)
        unverified.extend(report.unverified)
        if request.mode is Mode.NET_NEW:
            netnew_ops += len(report.ops)

    for report in reports_by_mode[Mode.DERIVATIVE]:
        derivative.update({comment.requirement_id: comment.verdict for comment in report.comments})
    for report in reports_by_mode[Mode.NET_NEW]:
        netnew.update({comment.requirement_id: comment.verdict for comment in report.comments})

    return FleetOutcome(
        status=run.result.status,
        attachments=len(run.outbound.attachments),
        checker_passed="PASS  156/156 checks passed" in run.checker_output,
        unverified=unverified,
        derivative_verdicts=derivative,
        netnew_verdicts=netnew,
        netnew_ops=netnew_ops,
    )


async def _run_fleet(_case: dict[str, Any]) -> FleetOutcome:
    return _outcome(await run_demo(live_model=True))


def _load_cases() -> tuple[str, list[Case[dict[str, Any], FleetOutcome, None]], float]:
    specification: dict[str, Any] = yaml.safe_load(_CASES_PATH.read_text(encoding="utf-8"))
    cases = [
        Case(name=case["name"], inputs={"expected_failures": case["expected_failures"]})
        for case in specification["cases"]
    ]
    return specification["name"], cases, float(specification["cases"][0]["max_duration_seconds"])


def main() -> int:
    if os.environ.get(_LIVE_EVAL_FLAG, "").strip().lower() not in {"1", "true", "yes"}:
        print(f"Set {_LIVE_EVAL_FLAG}=1 to run the live evaluation.", file=sys.stderr)
        return 2
    if not os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip():
        print("Set GOOGLE_CLOUD_PROJECT before running the live evaluation.", file=sys.stderr)
        return 2

    name, cases, max_duration = _load_cases()
    report = Dataset(
        name=name,
        cases=cases,
        evaluators=[FleetStructuralEval(), MaxDuration(seconds=max_duration)],
    ).evaluate_sync(_run_fleet, progress=False)
    report.print(include_input=False, include_output=True)

    if report.failures or not report.cases:
        print("Live evaluation could not complete successfully.", file=sys.stderr)
        return 1
    passed = all(
        score.value == 1.0
        for case in report.cases
        for score in case.scores.values()
        if score.name != "duration"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())