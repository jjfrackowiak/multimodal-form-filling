"""Manually run the B6 derivative flow against the fixture using Vertex ADC.

Run from the repository root after configuring Application Default Credentials:

    uv run python evals/b6/run.py

This is intentionally outside pytest. It calls ``review_derivative`` with ``model=None``
so the editor service resolves its configured, real Gemini model.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
for source_path in (
    ROOT / "packages" / "mff-contracts" / "src",
    ROOT / "services" / "editor-service" / "src",
):
    sys.path.insert(0, str(source_path))

from editor_service.flows.derivative import review_derivative
from mff_contracts import (
    BlobRef,
    Constraint,
    DerivativeArtifact,
    ImageAnalysis,
    Mode,
    Node,
    Requirement,
    SliceReport,
    SliceRequest,
)
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext, MaxDuration


@dataclass(frozen=True)
class EvalInput:
    """All fixture-backed inputs required to execute one derivative review."""

    job_id: str
    form_id: str
    requirements: list[Requirement]
    artifact: DerivativeArtifact
    inventory: list[ImageAnalysis]


@dataclass(frozen=True)
class StructuralSpec:
    expected_verdicts: dict[str, str]
    expected_verdict_counts: dict[str, int]
    governing_section_ids: dict[str, str]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        data = yaml.safe_load(source)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return cast(dict[str, Any], data)


def _load_requirements(path: Path) -> list[Requirement]:
    data = _load_yaml(path)
    raw_requirements = data.get("requirements")
    if not isinstance(raw_requirements, list):
        raise ValueError(f"Expected requirements list in {path}")

    requirements: list[Requirement] = []
    for raw_requirement in raw_requirements:
        if not isinstance(raw_requirement, dict):
            raise ValueError(f"Expected requirement mapping in {path}")
        requirement = dict(raw_requirement)
        requirement.pop("scope", None)
        if constraint := requirement.get("constraint"):
            if not isinstance(constraint, dict):
                raise ValueError(f"Expected constraint mapping in {path}")
            constraint_data = dict(constraint)
            constraint_data["source_span"] = constraint_data.pop("constraint_source_span")
            constraint_data["source_line"] = constraint_data.pop("constraint_source_line")
            requirement["constraint"] = Constraint.model_validate(constraint_data)
        requirements.append(Requirement.model_validate(requirement))
    return requirements


def _build_artifact(job_id: str, form_id: str, document_path: Path, structure: dict[str, Any]) -> DerivativeArtifact:
    document = structure.get("common", {}).get("document", {})
    headings = document.get("required_headings")
    if not isinstance(headings, list) or not all(isinstance(heading, str) for heading in headings):
        raise ValueError("Structure fixture must define common.document.required_headings")
    payload = document_path.read_bytes()
    return DerivativeArtifact(
        job_id=job_id,
        form_id=form_id,
        source=BlobRef(
            uri=document_path.resolve().as_uri(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        ),
        nodes=[
            Node(id=f"section-{index}", kind="heading", text=heading)
            for index, heading in enumerate(headings, start=1)
        ],
    )


def _load_spec(path: Path, review_path: Path) -> StructuralSpec:
    data = _load_yaml(path)
    review_data = _load_yaml(review_path)
    golden_verdicts = {
        verdict["requirement_id"]: verdict["verdict"] for verdict in review_data["verdicts"]
    }
    specified_verdicts = cast(dict[str, str], data["expected_verdicts"])
    if golden_verdicts != specified_verdicts:
        raise ValueError("structural-spec.yaml verdicts must exactly match the fixture review.yaml")
    return StructuralSpec(
        expected_verdicts=golden_verdicts,
        expected_verdict_counts=cast(dict[str, int], data["expected_verdict_counts"]),
        governing_section_ids=cast(dict[str, str], data["governing_section_ids"]),
    )


def _reason(value: bool, reason: str) -> EvaluationReason:
    return EvaluationReason(value=value, reason=None if value else reason)


@dataclass
class DerivativeStructure(Evaluator[EvalInput, SliceReport, StructuralSpec]):
    """Score only deterministic B6 output invariants; this is not an LLM judge."""

    def evaluate(
        self, ctx: EvaluatorContext[EvalInput, SliceReport, StructuralSpec]
    ) -> dict[str, EvaluationReason]:
        spec = ctx.expected_output
        if spec is None:
            raise ValueError("DerivativeStructure requires an expected structural specification")

        comments = ctx.output.comments
        actual_by_id = {comment.requirement_id: comment for comment in comments}
        expected_ids = set(spec.expected_verdicts)
        actual_ids = set(actual_by_id)
        known_node_ids = {node.id for node in ctx.inputs.artifact.nodes}
        actual_verdicts = {
            requirement_id: comment.verdict for requirement_id, comment in actual_by_id.items()
        }
        verdict_counts = {
            verdict: sum(comment.verdict == verdict for comment in comments)
            for verdict in spec.expected_verdict_counts
        }

        return {
            "exact_golden_verdicts": _reason(
                actual_verdicts == spec.expected_verdicts,
                f"expected verdicts {spec.expected_verdicts}, got {actual_verdicts}",
            ),
            "one_comment_per_requirement": _reason(
                len(comments) == len(expected_ids) and actual_ids == expected_ids,
                f"expected exactly {sorted(expected_ids)}, got {[comment.requirement_id for comment in comments]}",
            ),
            "verdict_counts": _reason(
                verdict_counts == spec.expected_verdict_counts,
                f"expected counts {spec.expected_verdict_counts}, got {verdict_counts}",
            ),
            "nonempty_justifications": _reason(
                all(comment.justification.strip() for comment in comments),
                "at least one comment has an empty justification",
            ),
            "valid_governing_anchors": _reason(
                len(comments) == len(expected_ids)
                and actual_ids == expected_ids
                and all(
                    comment.anchor.kind == "node"
                    and comment.anchor.target_id in known_node_ids
                    and comment.anchor.target_id == spec.governing_section_ids.get(comment.requirement_id)
                    for comment in comments
                ),
                "at least one comment does not target its governing heading node",
            ),
            "fail_suggestions_only": _reason(
                len(comments) == len(expected_ids)
                and actual_ids == expected_ids
                and all(
                    bool(comment.suggestion and comment.suggestion.strip())
                    if comment.verdict == "fail"
                    else comment.suggestion is None
                    for comment in comments
                ),
                "fail comments need suggestions and non-fail comments must omit them",
            ),
            "no_draft_ops": _reason(not ctx.output.ops, f"unexpected DraftOps: {ctx.output.ops}"),
            "no_unverified": _reason(
                not ctx.output.unverified,
                f"unverified requirements: {ctx.output.unverified}",
            ),
        }


async def _review_all_slices(inputs: EvalInput) -> SliceReport:
    """Run the production B6 entry point for each six-requirement derivative slice."""
    reports: list[SliceReport] = []
    ordered = sorted(inputs.requirements, key=lambda requirement: (requirement.ordinal, requirement.text))
    for index, start in enumerate(range(0, len(ordered), 6), start=1):
        request = SliceRequest(
            job_id=inputs.job_id,
            slice_id=f"slice-{index:02d}",
            mode=Mode.DERIVATIVE,
            requirements=ordered[start : start + 6],
            artifact=inputs.artifact,
        )
        reports.append(
            await review_derivative(request, inputs.artifact, inputs.inventory, model=None)
        )
    return SliceReport(
        slice_id="fixture-fleet-vehicle-return",
        comments=[comment for report in reports for comment in report.comments],
        ops=[operation for report in reports for operation in report.ops],
        unverified=[requirement_id for report in reports for requirement_id in report.unverified],
        attempts_used=sum(report.attempts_used for report in reports),
    )


def _build_dataset() -> Dataset[EvalInput, SliceReport, StructuralSpec]:
    cases_config = _load_yaml(Path(__file__).with_name("cases.yaml"))
    fixture_paths = cast(dict[str, str], cases_config["fixtures"])
    case_config = cast(dict[str, Any], cases_config["cases"][0])
    requirements = _load_requirements(ROOT / fixture_paths["requirements"])
    inventory_data = _load_yaml(ROOT / fixture_paths["inventory"])
    inventory = [ImageAnalysis.model_validate(image) for image in inventory_data["images"]]
    structure = _load_yaml(ROOT / fixture_paths["structure"])
    artifact = _build_artifact(
        job_id=case_config["job_id"],
        form_id=case_config["form_id"],
        document_path=ROOT / fixture_paths["document"],
        structure=structure,
    )
    spec = _load_spec(
        Path(__file__).with_name("structural-spec.yaml"),
        ROOT / fixture_paths["review"],
    )
    input_value = EvalInput(
        job_id=case_config["job_id"],
        form_id=case_config["form_id"],
        requirements=requirements,
        artifact=artifact,
        inventory=inventory,
    )
    return Dataset(
        name=cases_config["name"],
        cases=[
            Case(
                name=case_config["name"],
                inputs=input_value,
                expected_output=spec,
            )
        ],
        evaluators=(
            MaxDuration(seconds=float(case_config["max_duration_seconds"])),
            DerivativeStructure(),
        ),
    )


def _report_failed(report: Any) -> bool:
    return bool(
        report.failures
        or report.report_evaluator_failures
        or any(case.evaluator_failures for case in report.cases)
        or any(not result.value for case in report.cases for result in case.assertions.values())
    )


async def _main(repeat: int) -> int:
    dataset = _build_dataset()
    report = await dataset.evaluate(
        _review_all_slices,
        max_concurrency=1,
        progress=True,
        repeat=repeat,
        metadata={"model": "editor default (model=None)", "auth": "Vertex ADC"},
    )
    report.print(include_reasons=True)
    return 1 if _report_failed(report) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1, help="Number of live runs per case")
    arguments = parser.parse_args()
    if arguments.repeat < 1:
        parser.error("--repeat must be at least 1")
    return asyncio.run(_main(arguments.repeat))


if __name__ == "__main__":
    raise SystemExit(main())