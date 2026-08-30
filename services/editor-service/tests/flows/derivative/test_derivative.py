from __future__ import annotations

import pytest

from editor_service.flows.derivative import DERIVATIVE_INSTRUCTION, review_derivative
from editor_service.llm.output import SliceTurnOutput
from mff_contracts import (
    Anchor,
    BlobRef,
    DerivativeArtifact,
    ImageAnalysis,
    Mode,
    Node,
    Requirement,
    RequirementHit,
    ReviewComment,
    SliceReport,
    SliceRequest,
)
from mff_fakes import FakeLlm

JOB_ID = "job-fleet-vehicle-return"
FORM_ID = "form_supplied.docx"
SLICE_ID = "slice-01"
SECTION_IDS = {
    "R-01": "section-1",
    "R-02": "section-2",
    "R-03": "section-3",
    "R-04": "section-4",
    "R-05": "section-5",
    "R-06": "section-5",
    "R-07": "section-6",
    "R-08": "section-7",
    "R-09": "section-7",
    "R-10": "section-8",
}
REQUIREMENT_TEXT = {
    "R-01": "A photograph of the engine bay, taken with the bonnet open.",
    "R-02": "Four photographs of the seats.",
    "R-03": "Two photographs of the vehicle taken on the diagonal.",
    "R-04": "Two photographs of the headliner from between the front seats.",
    "R-05": "A photograph of the windscreen taken from inside the cabin.",
    "R-06": "A photograph of the windscreen taken from outside the vehicle.",
    "R-07": "A photograph of the tyre tread.",
    "R-08": "A photograph of the boot with the tailgate open.",
    "R-09": "A photograph of the under-floor equipment.",
    "R-10": "A photograph of the instrument cluster.",
}


def _requirements() -> list[Requirement]:
    result: list[Requirement] = []
    for index, (requirement_id, text) in enumerate(REQUIREMENT_TEXT.items(), start=1):
        expected_count = (
            4
            if requirement_id == "R-02"
            else 2
            if requirement_id in {"R-01", "R-03", "R-04"}
            else 1
        )
        result.append(
            Requirement(
                id=requirement_id,
                ordinal=index,
                source_line=index,
                source_span=requirement_id,
                text=text,
                expected_count=expected_count,
            )
        )
    return result


def _artifact() -> DerivativeArtifact:
    headings = [
        "1. Pod maską",
        "2. Fotele",
        "3. Przekątne pojazdu",
        "4. Podsufitka",
        "5. Przednia szyba",
        "6. Bieżnik opony",
        "7. Bagażnik i wyposażenie",
        "8. Zegary",
        "9. Uwagi",
    ]
    return DerivativeArtifact(
        job_id=JOB_ID,
        form_id=FORM_ID,
        source=BlobRef(
            uri="gs://mff-local/jobs/job-fleet-vehicle-return/source/source.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=1,
            sha256="0" * 64,
        ),
        nodes=[
            Node(id=f"section-{index}", kind="heading", text=heading)
            for index, heading in enumerate(headings, start=1)
        ],
    )


def _request() -> SliceRequest:
    return SliceRequest(
        job_id=JOB_ID,
        slice_id=SLICE_ID,
        mode=Mode.DERIVATIVE,
        requirements=_requirements(),
        artifact=_artifact(),
    )


def _inventory() -> list[ImageAnalysis]:
    entries = [
        ("IMG_20260830_132754 (4).jpg", "R-01", None),
        ("IMG_20260830_132755 (1).jpg", "R-02", None),
        ("IMG_20260830_132755.jpg", "R-02", None),
        ("IMG_20260830_132755 (2).jpg", "R-02", None),
        ("IMG_20260830_132755 (3).jpg", "R-02", None),
        ("IMG_20260830_132755 (10).jpg", "R-03", None),
        ("IMG_20260830_132755 (9).jpg", "R-03", None),
        ("1000040420.jpg", "R-04", (True, "both front headrests in frame")),
        ("IMG_20260830_132755 (5).jpg", "R-04", (False, "shot from a side position")),
        ("IMG_20260830_132754.jpg", "R-05", None),
        ("IMG_20260830_132754 (1).jpg", "R-06", None),
        ("IMG_20260830_132755 (4).jpg", "R-07", None),
        ("1000040429.jpg", "R-08", None),
        ("IMG_20260830_132603.jpg", "R-09", None),
        ("IMG_20260830_132754 (2).jpg", "R-10", None),
    ]
    result: list[ImageAnalysis] = []
    for filename, requirement_id, constraint in entries:
        if constraint is None:
            hit = RequirementHit(id=requirement_id)
        else:
            constraint_ok, evidence = constraint
            hit = RequirementHit(
                id=requirement_id,
                constraint_ok=constraint_ok,
                constraint_evidence=evidence,
            )
        result.append(ImageAnalysis(file=filename, hits=[hit]))
    return result


def _comment(
    requirement_id: str,
    verdict: str,
    justification: str,
    suggestion: str | None = None,
) -> ReviewComment:
    return ReviewComment(
        requirement_id=requirement_id,
        anchor=Anchor(kind="node", target_id=SECTION_IDS[requirement_id]),
        verdict=verdict,
        justification=justification,
        suggestion=suggestion,
    )


def _golden_comments() -> list[ReviewComment]:
    return [
        _comment(
            "R-01",
            "fail",
            "Two engine-bay photographs were required; "
            "IMG_20260830_132754 (4).jpg is the only supplied engine-bay photo.",
            "Supply a second photograph under the bonnet from a different angle.",
        ),
        _comment(
            "R-02",
            "pass",
            "Four seat photographs supplied: IMG_20260830_132755 (1).jpg, "
            "IMG_20260830_132755.jpg, IMG_20260830_132755 (2).jpg, and "
            "IMG_20260830_132755 (3).jpg.",
        ),
        _comment(
            "R-03",
            "pass",
            "IMG_20260830_132755 (10).jpg and IMG_20260830_132755 (9).jpg "
            "supply front and rear three-quarter views.",
        ),
        _comment(
            "R-04",
            "fail",
            "Two headliner photographs were supplied, but only 1000040420.jpg "
            "meets the between-front-seats constraint; "
            "IMG_20260830_132755 (5).jpg is a side-position view.",
            "Retake IMG_20260830_132755 (5).jpg from between the two front seats, "
            "as in 1000040420.jpg.",
        ),
        _comment(
            "R-05",
            "pass",
            "IMG_20260830_132754.jpg shows the windscreen from inside the cabin "
            "with the dashboard and mirror visible.",
        ),
        _comment(
            "R-06",
            "pass",
            "IMG_20260830_132754 (1).jpg shows the windscreen from outside with "
            "the occupant visible through the glass.",
        ),
        _comment("R-07", "pass", "IMG_20260830_132755 (4).jpg shows the tyre tread."),
        _comment("R-08", "pass", "1000040429.jpg shows the boot with the tailgate open."),
        _comment(
            "R-09",
            "pass",
            "IMG_20260830_132603.jpg shows the spare wheel, tool kit, fire "
            "extinguisher, and warning triangle.",
        ),
        _comment("R-10", "pass", "IMG_20260830_132754 (2).jpg shows the instrument cluster."),
    ]


async def _run(comments: list[ReviewComment]) -> tuple[SliceReport, FakeLlm]:
    fake = FakeLlm.script([SliceTurnOutput(comments=comments)])
    report = await review_derivative(_request(), _artifact(), _inventory(), model=fake)
    return report, fake


def _assert_structural_golden(report: SliceReport) -> None:
    expected = {comment.requirement_id: comment for comment in _golden_comments()}
    actual = {comment.requirement_id: comment for comment in report.comments}
    known_node_ids = {node.id for node in _artifact().nodes}

    assert len(actual) == 10
    assert set(actual) == set(expected)
    assert {comment.verdict for comment in actual.values()} == {"pass", "fail"}
    assert sum(comment.verdict == "pass" for comment in actual.values()) == 8
    assert sum(comment.verdict == "fail" for comment in actual.values()) == 2
    assert all(comment.justification.strip() for comment in actual.values())
    assert all(comment.anchor.target_id in known_node_ids for comment in actual.values())
    assert all(
        comment.suggestion is None for comment in actual.values() if comment.verdict == "pass"
    )
    assert all(
        comment.suggestion and comment.suggestion.strip()
        for comment in actual.values()
        if comment.verdict == "fail"
    )
    for requirement_id, expected_comment in expected.items():
        assert actual[requirement_id].verdict == expected_comment.verdict


async def test_r01_fails_when_only_one_of_two_engine_photos_is_supplied() -> None:
    report, _fake = await _run(_golden_comments())

    r01 = {comment.requirement_id: comment for comment in report.comments}["R-01"]
    assert r01.verdict == "fail"
    assert "IMG_20260830_132754 (4).jpg" in r01.justification
    assert r01.suggestion


async def test_r04_fails_when_count_is_met_but_constraint_is_not() -> None:
    report, _fake = await _run(_golden_comments())

    r04 = {comment.requirement_id: comment for comment in report.comments}["R-04"]
    assert r04.verdict == "fail"
    assert "1000040420.jpg" in r04.justification
    assert "IMG_20260830_132755 (5).jpg" in r04.justification
    assert r04.suggestion


async def test_all_eight_passing_requirements_have_specific_justifications() -> None:
    report, _fake = await _run(_golden_comments())

    passing = [comment for comment in report.comments if comment.verdict == "pass"]
    assert len(passing) == 8
    assert {comment.requirement_id for comment in passing} == {
        "R-02",
        "R-03",
        "R-05",
        "R-06",
        "R-07",
        "R-08",
        "R-09",
        "R-10",
    }
    assert all(comment.justification.strip() for comment in passing)
    assert all(comment.suggestion is None for comment in passing)


async def test_golden_review_is_structurally_reproducible_and_derivative_has_no_ops() -> None:
    report, _fake = await _run(_golden_comments())

    _assert_structural_golden(report)
    assert report.ops == []
    assert report.unverified == []
    assert report.attempts_used == 1


async def test_mutating_r04_to_pass_is_caught_by_structural_eval() -> None:
    mutated = [
        _comment(
            comment.requirement_id,
            "pass" if comment.requirement_id == "R-04" else comment.verdict,
            comment.justification,
            None if comment.requirement_id == "R-04" else comment.suggestion,
        )
        for comment in _golden_comments()
    ]
    report, _fake = await _run(mutated)

    with pytest.raises(AssertionError):
        _assert_structural_golden(report)


async def test_inventory_is_injected_as_structured_context() -> None:
    report, fake = await _run(_golden_comments())

    assert report.unverified == []
    request_text = str(fake.requests[-1])
    assert "section-4" in request_text
    assert "4. Podsufitka" in request_text
    assert "1000040420.jpg" in request_text
    assert "constraint_ok" in request_text
    assert "IMG_20260830_132755 (5).jpg" in request_text
    assert "do not re-analyse photos" in request_text.lower()


async def test_derivative_keeps_supplied_nodes_unchanged() -> None:
    artifact = _artifact()
    original_nodes = artifact.model_copy(deep=True).nodes
    fake = FakeLlm.script([SliceTurnOutput(comments=_golden_comments())])

    await review_derivative(_request(), artifact, _inventory(), model=fake)

    assert artifact.nodes == original_nodes


def test_instruction_is_a_substantial_derivative_policy() -> None:
    assert len(DERIVATIVE_INSTRUCTION) >= 200
    policy = DERIVATIVE_INSTRUCTION.lower()
    assert "pass" in policy and "fail" in policy
    assert "constraint" in policy
    assert "justification" in policy
    assert "suggestion" in policy
    assert "constraint_ok" in policy
    assert "constraint_evidence" in policy


async def test_derivative_rejects_a_net_new_request() -> None:
    request = _request().model_copy(update={"mode": Mode.NET_NEW})
    fake = FakeLlm.script([SliceTurnOutput(comments=[])])

    with pytest.raises(ValueError, match="derivative"):
        await review_derivative(request, _artifact(), _inventory(), model=fake)


def test_fake_llm_is_the_only_model_used_by_this_suite() -> None:
    fake = FakeLlm.script([])

    assert fake.model == "fake-llm"
