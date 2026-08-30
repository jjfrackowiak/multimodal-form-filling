"""The retry loop — brief DoD 4, 5, 10.

Every test here scripts `FakeLlm` directly with `LlmAgent(model=fake, ...)`: `build_agent`
is not used, because production `build_agent` resolves a real, ADC-authenticated Gemini
client and these tests must never touch a network (brief DoD 2). See
`test_build_agent.py::test_build_agent_wires_...` for proof `build_agent` itself is wired
correctly; this module is entirely about `run_slice`'s own retry lifecycle.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from mff_fakes import FakeLlm

from editor_service.llm.deps import EditorDeps
from editor_service.llm.output import SliceTurnOutput
from editor_service.llm.run import run_slice

from golden import GOLDEN_REQUIREMENTS, golden_artifact, golden_slice_request, make_comment

REQUIREMENT_IDS = [r.id for r in GOLDEN_REQUIREMENTS]


def _agent(fake: FakeLlm) -> LlmAgent:
    return LlmAgent(
        name="reviewer",
        model=fake,
        instruction="review each requirement",
        output_schema=SliceTurnOutput,
        tools=[],
    )


async def test_clean_run_settles_everything_in_one_attempt() -> None:
    turn_output = SliceTurnOutput(comments=[make_comment(rid) for rid in REQUIREMENT_IDS])
    fake = FakeLlm.script([turn_output])
    deps = EditorDeps(artifact=golden_artifact(), agent=_agent(fake))

    report = await run_slice(golden_slice_request(), deps)

    assert report.attempts_used == 1
    assert report.unverified == []
    assert {c.requirement_id for c in report.comments} == set(REQUIREMENT_IDS)
    assert len(fake.requests) == 1


async def test_three_failed_attempts_return_well_formed_report_with_unverified() -> None:
    """Force validation failure on every attempt (empty comments each turn): after three
    attempts the stragglers are marked `unverified`, `attempts_used == 3`, and — the whole
    point — nothing raises."""
    empty = SliceTurnOutput(comments=[])
    fake = FakeLlm.script([empty, empty, empty])
    deps = EditorDeps(artifact=golden_artifact(), agent=_agent(fake))

    report = await run_slice(golden_slice_request(), deps)

    assert report.attempts_used == 3
    assert set(report.unverified) == set(REQUIREMENT_IDS)
    assert report.comments == []
    assert len(fake.requests) == 3


async def test_provider_error_is_caught_and_still_returns_well_formed_report() -> None:
    """No ADK or provider exception may escape to the orchestrator (brief). Scripting zero
    responses with an `error=` makes every attempt raise inside `generate_content_async`;
    `run_slice` must still return normally."""
    fake = FakeLlm.script([], error=RuntimeError("simulated transport failure"))
    deps = EditorDeps(artifact=golden_artifact(), agent=_agent(fake))

    report = await run_slice(golden_slice_request(), deps)

    assert report.attempts_used == 3
    assert set(report.unverified) == set(REQUIREMENT_IDS)
    assert report.comments == []


async def test_unresolvable_anchor_is_a_validation_failure_not_a_pass() -> None:
    """`validate` checks anchor resolution deterministically — a comment pointing at a node
    id absent from the artifact must not be accepted as settled."""
    bad = SliceTurnOutput(
        comments=[make_comment(rid, target_id="node-does-not-exist") for rid in REQUIREMENT_IDS]
    )
    good = SliceTurnOutput(comments=[make_comment(rid) for rid in REQUIREMENT_IDS])
    fake = FakeLlm.script([bad, good])
    deps = EditorDeps(artifact=golden_artifact(), agent=_agent(fake))

    report = await run_slice(golden_slice_request(), deps)

    assert report.attempts_used == 2
    assert report.unverified == []
    assert {c.requirement_id for c in report.comments} == set(REQUIREMENT_IDS)


async def test_settled_answer_never_revisited() -> None:
    """Rule 2, tested directly: R-01 passes on attempt 1. Attempt 2's output changes R-01's
    verdict/justification and answers R-02 (which attempt 1 left pending). The final report
    must keep attempt 1's exact R-01 comment, not attempt 2's."""
    two_requirements = GOLDEN_REQUIREMENTS[:2]
    original_r01 = make_comment(
        "R-01", verdict="pass", justification="Attempt 1: engine bay photographed correctly."
    )
    turn1 = SliceTurnOutput(comments=[original_r01])  # R-02 left pending on purpose

    changed_r01 = make_comment(
        "R-01", verdict="fail", justification="Attempt 2 changed its mind — must be ignored.",
        suggestion="Retake the photo.",
    )
    turn2 = SliceTurnOutput(comments=[changed_r01, make_comment("R-02")])

    fake = FakeLlm.script([turn1, turn2])
    deps = EditorDeps(artifact=golden_artifact(), agent=_agent(fake))
    req = golden_slice_request(requirements=two_requirements)

    report = await run_slice(req, deps)

    assert report.attempts_used == 2
    assert report.unverified == []
    by_id = {c.requirement_id: c for c in report.comments}
    assert by_id["R-01"] is original_r01 or by_id["R-01"] == original_r01
    assert by_id["R-01"].justification == "Attempt 1: engine bay photographed correctly."
    assert by_id["R-01"].verdict == "pass"
    assert by_id["R-02"].requirement_id == "R-02"


async def test_ops_are_copied_from_op_log_verbatim() -> None:
    """`ops` never comes from structured JSON output — mutation tools append to
    `deps.op_log` directly (see `llm/deps.py`), and `run_slice` copies it into the report
    unchanged. Simulated here without a real tool: append to `op_log` before running."""
    from mff_contracts import DraftOp

    turn_output = SliceTurnOutput(comments=[make_comment(rid) for rid in REQUIREMENT_IDS])
    fake = FakeLlm.script([turn_output])
    deps = EditorDeps(artifact=golden_artifact(), agent=_agent(fake))
    deps.op_log.append(
        DraftOp(kind="append", requirement_id="R-01", section_id="sec-1", value="hello")
    )

    report = await run_slice(golden_slice_request(), deps)

    assert len(report.ops) == 1
    assert report.ops[0].requirement_id == "R-01"
