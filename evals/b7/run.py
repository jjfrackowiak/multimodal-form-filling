"""Run the B7 net-new flow against the fleet fixture as an opt-in live evaluation.

This is intentionally a standalone command rather than a pytest test. It calls the real
default Gemini configuration through ``compose_netnew(..., model=None)`` and scores only
deterministic properties of the returned report and generated draft.
"""

from __future__ import annotations

import io
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from docx import Document
from pydantic import BaseModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, MaxDuration

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from editor_service.flows.netnew import (  # noqa: E402
    SCAFFOLD_SECTIONS,
    _ensure_scaffold,
    compose_netnew,
)
from mff_applier import apply_slice  # noqa: E402
from mff_contracts import (  # noqa: E402
    Constraint,
    FormDraft,
    ImageAnalysis,
    Mode,
    NetNewArtifact,
    Requirement,
    Section,
    SliceRequest,
)
from mff_docmodel import compile_netnew  # noqa: E402

_LIVE_EVAL_FLAG = "MFF_B7_LIVE_EVAL"
_CASES_PATH = Path(__file__).with_name("cases.yaml")
_STRUCTURE_PATH = Path(__file__).with_name("structure.yaml")
_DEFAULT_EDITOR_MODEL_ID = "gemini-2.5-flash"


class NetNewOutcome(BaseModel):
    """The serialisable, structural result of one live B7 flow invocation."""

    verdicts: dict[str, str]
    comment_requirement_ids: list[str]
    unverified: list[str]
    anchors: list[str | None]
    draft_entry_ids: list[str]
    operation_count: int
    applier_rejection_count: int
    compiled_draft_opens: bool
    rendered_entry_ids: list[str]
    model_id: str


class NetNewStructuralEval(Evaluator[dict[str, Any], NetNewOutcome]):
    """Assert the B7 fixture specification without asking another model to judge it."""

    def evaluate(self, ctx: EvaluatorContext[dict[str, Any], NetNewOutcome]) -> dict[str, float]:
        outcome = ctx.output
        specification = ctx.inputs["structure"]
        requirement_ids = specification["requirements"]["ids"]
        shortfalls = set(specification["requirements"]["shortfalls"])
        expected_verdicts = {
            requirement_id: "shortfall" if requirement_id in shortfalls else "realised"
            for requirement_id in requirement_ids
        }
        comment_counts = Counter(outcome.comment_requirement_ids)
        expected_entry_ids = set(outcome.draft_entry_ids)
        return {
            "expected_verdicts": float(outcome.verdicts == expected_verdicts),
            "r01_shortfall": float(outcome.verdicts.get("R-01") == "shortfall"),
            "r04_shortfall": float(outcome.verdicts.get("R-04") == "shortfall"),
            "other_requirements_realised": float(
                sum(verdict == "realised" for verdict in outcome.verdicts.values())
                == specification["requirements"]["realised_count"]
            ),
            "all_requirements_settled": float(not outcome.unverified),
            "one_comment_per_requirement": float(
                set(comment_counts) == set(requirement_ids)
                and all(comment_counts[requirement_id] == 1 for requirement_id in requirement_ids)
            ),
            "anchors_resolve_to_draft_entries": float(
                bool(outcome.anchors) and all(anchor in expected_entry_ids for anchor in outcome.anchors)
            ),
            "draft_operations_present": float(outcome.operation_count > 0),
            "draft_operations_apply_without_rejection": float(outcome.applier_rejection_count == 0),
            "compiled_draft_opens": float(outcome.compiled_draft_opens),
            "rendered_draft_covers_all_entries": float(
                set(outcome.rendered_entry_ids) == expected_entry_ids
            ),
        }


def _load_requirements(path: Path) -> list[Requirement]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    requirements: list[Requirement] = []
    for raw_requirement in data["requirements"]:
        requirement_data = dict(raw_requirement)
        constraint_data = requirement_data.pop("constraint", None)
        if constraint_data is not None:
            constraint = dict(constraint_data)
            constraint["source_span"] = constraint.pop("constraint_source_span")
            constraint["source_line"] = constraint.pop("constraint_source_line")
            requirement_data["constraint"] = Constraint.model_validate(constraint)
        requirements.append(Requirement.model_validate(requirement_data))
    return requirements


def _scaffolded_artifact(form_id: str) -> NetNewArtifact:
    return NetNewArtifact(
        job_id="eval-b7-fleet",
        form_id=form_id,
        draft=FormDraft(
            sections=[Section(id=section_id, title=title) for section_id, title in SCAFFOLD_SECTIONS]
        ),
    )


def _load_case_input(case: dict[str, Any]) -> tuple[list[Requirement], list[ImageAnalysis], dict[str, str]]:
    fixture_root = REPO_ROOT / case["fixture_root"]
    requirements = _load_requirements(fixture_root / case["requirements"])
    inventory_data: dict[str, Any] = yaml.safe_load(
        (fixture_root / case["inventory"]).read_text(encoding="utf-8")
    )
    inventory = [ImageAnalysis.model_validate(image) for image in inventory_data["images"]]
    input_dir = fixture_root / case["client_inputs"]
    client_texts = {
        text_file.name: text_file.read_text(encoding="utf-8")
        for text_file in sorted(input_dir.glob("*.txt"))
    }
    return requirements, inventory, client_texts


async def _run_case(case: dict[str, Any]) -> NetNewOutcome:
    requirements, inventory, client_texts = _load_case_input(case)
    artifact = _scaffolded_artifact(case["form_id"])
    _ensure_scaffold(artifact, requirements)
    original = artifact.model_copy(deep=True)
    request = SliceRequest(
        job_id=artifact.job_id,
        slice_id="eval-b7-netnew",
        mode=Mode.NET_NEW,
        requirements=requirements,
        artifact=artifact,
        scope_ids=[section_id for section_id, _title in SCAFFOLD_SECTIONS],
    )
    report = await compose_netnew(request, artifact, inventory, client_texts, model=None)
    applied = apply_slice(original, report, request.scope_ids)
    compiled_bytes, render_map = compile_netnew(artifact)
    try:
        Document(io.BytesIO(compiled_bytes))
        compiled_draft_opens = True
    except Exception:
        compiled_draft_opens = False

    return NetNewOutcome(
        verdicts={comment.requirement_id: comment.verdict for comment in report.comments},
        comment_requirement_ids=[comment.requirement_id for comment in report.comments],
        unverified=report.unverified,
        anchors=[comment.anchor.target_id for comment in report.comments],
        draft_entry_ids=[entry.id for section in artifact.draft.sections for entry in section.entries],
        operation_count=len(report.ops),
        applier_rejection_count=len(applied.rejected),
        compiled_draft_opens=compiled_draft_opens,
        rendered_entry_ids=list(render_map.anchor_to_span),
        model_id=os.environ.get("EDITOR_MODEL_ID", _DEFAULT_EDITOR_MODEL_ID),
    )


def _load_dataset() -> tuple[str, list[Case[dict[str, Any], NetNewOutcome, None]], float]:
    case_data: dict[str, Any] = yaml.safe_load(_CASES_PATH.read_text(encoding="utf-8"))
    structure: dict[str, Any] = yaml.safe_load(_STRUCTURE_PATH.read_text(encoding="utf-8"))
    cases = [
        Case(name=case["name"], inputs={"case": case, "structure": structure})
        for case in case_data["cases"]
    ]
    durations = [float(case["max_duration_seconds"]) for case in case_data["cases"]]
    return case_data["name"], cases, max(durations)


async def _task(inputs: dict[str, Any]) -> NetNewOutcome:
    return await _run_case(inputs["case"])


def main() -> int:
    if os.environ.get(_LIVE_EVAL_FLAG, "").strip().lower() not in {"1", "true", "yes"}:
        print(f"Set {_LIVE_EVAL_FLAG}=1 to run the live evaluation.", file=sys.stderr)
        return 2
    if not os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip():
        print("Set GOOGLE_CLOUD_PROJECT before running the live evaluation.", file=sys.stderr)
        return 2

    name, cases, max_duration = _load_dataset()
    report = Dataset(
        name=name,
        cases=cases,
        evaluators=[NetNewStructuralEval(), MaxDuration(seconds=max_duration)],
    ).evaluate_sync(_task, progress=False)
    report.print(include_input=False, include_output=True)

    if report.failures or not report.cases:
        print("Live evaluation could not complete successfully.", file=sys.stderr)
        return 1
    passed = all(
        score.value == 1.0
        for case_result in report.cases
        for score in case_result.scores.values()
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())