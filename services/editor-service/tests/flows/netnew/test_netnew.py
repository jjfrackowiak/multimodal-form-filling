from __future__ import annotations

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from editor_service.flows.netnew import NET_NEW_INSTRUCTION, SCAFFOLD_SECTIONS, compose_netnew
from editor_service.flows.tools import make_tools
from editor_service.llm.deps import EditorDeps
from editor_service.llm.output import SliceTurnOutput
from mff_applier import apply_slice
from mff_contracts import (
    Anchor,
    DerivativeArtifact,
    Entry,
    FormDraft,
    ImageAnalysis,
    Mode,
    NetNewArtifact,
    Node,
    Requirement,
    ReviewComment,
    Section,
    SliceReport,
    SliceRequest,
)
from mff_fakes import FakeLlm

REQUIREMENTS = [
    Requirement(
        id=f"R-{number:02d}",
        ordinal=number,
        source_line=number,
        source_span=f"requirement {number}",
        text=f"Requirement {number} needs evidence.",
    )
    for number in range(1, 11)
]


def _artifact() -> NetNewArtifact:
    sections = [
        Section(
            id=section_id,
            title=title,
            entries=[
                Entry(
                    id=f"entry-R-{number:02d}",
                    order="m",
                    value=f"evidence for R-{number:02d}",
                    set_by=f"R-{number:02d}",
                ),
                *(
                    [
                        Entry(
                            id="entry-R-10",
                            order="n",
                            value="evidence for R-10",
                            set_by="R-10",
                        )
                    ]
                    if number == len(SCAFFOLD_SECTIONS)
                    else []
                ),
            ],
        )
        for number, (section_id, title) in enumerate(SCAFFOLD_SECTIONS, start=1)
    ]
    return NetNewArtifact(
        job_id="job-1",
        form_id="form-1",
        draft=FormDraft(sections=sections),
    )


def _comment(requirement_id: str, verdict: str) -> ReviewComment:
    return ReviewComment(
        requirement_id=requirement_id,
        anchor=Anchor(kind="entry", target_id=f"entry-{requirement_id}"),
        verdict=verdict,
        justification=f"The inventory identifies evidence for {requirement_id}.",
    )


def _request(artifact: NetNewArtifact) -> SliceRequest:
    return SliceRequest(
        job_id=artifact.job_id,
        slice_id="slice-01",
        mode=Mode.NET_NEW,
        requirements=REQUIREMENTS,
        artifact=artifact,
        scope_ids=[section_id for section_id, _title in SCAFFOLD_SECTIONS],
    )


def _deps(artifact: NetNewArtifact, fake: FakeLlm) -> EditorDeps:
    return EditorDeps(
        artifact=artifact,
        agent=LlmAgent(
            name="test",
            model=fake,
            instruction="test",
            output_schema=SliceTurnOutput,
            tools=[],
        ),
    )


def test_instruction_covers_netnew_policy() -> None:
    fake = FakeLlm.script([])

    assert len(NET_NEW_INSTRUCTION) >= 200
    assert "realised" in NET_NEW_INSTRUCTION
    assert "shortfall" in NET_NEW_INSTRUCTION
    assert "set_field" in NET_NEW_INSTRUCTION
    assert "append_entry" in NET_NEW_INSTRUCTION
    assert "delete_entry" in NET_NEW_INSTRUCTION
    assert fake.model == "fake-llm"


def test_mutation_tools_update_draft_and_log_provenance() -> None:
    artifact = _artifact()
    fake = FakeLlm.script([])
    deps = _deps(artifact, fake)
    set_field, append_entry, delete_entry = make_tools(deps)

    assert set_field("section-01", "entry-R-01", "updated", "R-02") == "ok"
    assert artifact.draft.sections[0].entries[0].value == "updated"
    assert artifact.draft.sections[0].entries[0].set_by == "R-02"

    assert append_entry("section-02", "Seats", "front left", "R-02") == "ok"
    appended = artifact.draft.sections[1].entries[-1]
    assert appended.value == "Seats: front left"
    assert appended.set_by == "R-02"

    assert delete_entry("section-02", appended.id, "R-03") == "ok"
    assert all(entry.id != appended.id for entry in artifact.draft.sections[1].entries)

    assert [op.kind for op in deps.op_log] == ["set", "append", "delete"]
    assert [op.requirement_id for op in deps.op_log] == ["R-02", "R-02", "R-03"]


def test_tools_reject_missing_targets_and_append_context() -> None:
    artifact = _artifact()
    fake = FakeLlm.script([])
    deps = _deps(artifact, fake)
    set_field, append_entry, delete_entry = make_tools(deps)

    assert set_field("section-01", "missing", "value") == "error: unknown entry 'missing'"
    assert set_field("section-02", "entry-R-01", "value") == (
        "error: entry 'entry-R-01' is not in section 'section-02'"
    )
    assert append_entry("missing", "label", "value", "R-01") == "error: unknown section 'missing'"
    assert append_entry("section-01", "label", "value") == (
        "error: requirement_id is required when appending an entry"
    )
    assert delete_entry("section-01", "missing") == "error: unknown entry 'missing'"
    assert delete_entry("section-02", "entry-R-01") == (
        "error: entry 'entry-R-01' is not in section 'section-02'"
    )
    assert deps.op_log == []


def test_tools_require_netnew_artifact() -> None:
    fake = FakeLlm.script([])
    derivative = DerivativeArtifact(
        job_id="job-1",
        form_id="form-1",
        source={
            "uri": "gs://bucket/source",
            "content_type": "application/octet-stream",
            "size_bytes": 1,
            "sha256": "0" * 64,
        },
        nodes=[Node(id="node-1", kind="paragraph", text="text")],
    )
    deps = EditorDeps(
        artifact=derivative,
        agent=LlmAgent(
            name="test",
            model=fake,
            instruction="test",
            output_schema=SliceTurnOutput,
            tools=[],
        ),
    )

    with pytest.raises(TypeError, match="NetNewArtifact"):
        make_tools(deps)


def test_tool_ops_are_accepted_by_apply_slice() -> None:
    original = _artifact()
    working = original.model_copy(deep=True)
    fake = FakeLlm.script([])
    deps = _deps(working, fake)
    set_field, append_entry, _delete_entry = make_tools(deps)
    set_field("section-01", "entry-R-01", "changed", "R-01")
    append_entry("section-01", "Extra", "photo", "R-01")
    report = SliceReport(slice_id="slice-01", ops=deps.op_log, attempts_used=1)

    result = apply_slice(original, report, ["section-01"])

    assert result.rejected == []
    assert isinstance(result.artifact, NetNewArtifact)
    assert result.artifact.draft.sections[0].entries[0].value == "changed"
    assert [entry.value for entry in result.artifact.draft.sections[0].entries] == [
        "changed",
        "Extra: photo",
    ]


def test_delete_tool_op_is_accepted_by_apply_slice_for_an_existing_entry() -> None:
    original = _artifact()
    working = original.model_copy(deep=True)
    fake = FakeLlm.script([])
    deps = _deps(working, fake)
    _set_field, _append_entry, delete_entry = make_tools(deps)

    assert delete_entry("section-01", "entry-R-01", "R-01") == "ok"
    report = SliceReport(slice_id="slice-01", ops=deps.op_log, attempts_used=1)

    result = apply_slice(original, report, ["section-01"])

    assert result.rejected == []
    assert isinstance(result.artifact, NetNewArtifact)
    assert result.artifact.draft.sections[0].entries == []


async def test_compose_netnew_returns_expected_verdicts_ops_and_resolved_anchors() -> None:
    artifact = _artifact()
    fake = FakeLlm.script(
        [
            LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="append_entry",
                                args={
                                    "section_id": "section-01",
                                    "label": "Engine photo",
                                    "value": "supplied",
                                    "requirement_id": "R-01",
                                },
                            )
                        )
                    ],
                )
            ),
            SliceTurnOutput(
                comments=[
                    _comment(
                        requirement.id,
                        "shortfall" if requirement.id in {"R-01", "R-04"} else "realised",
                    )
                    for requirement in REQUIREMENTS
                ]
            ),
            SliceTurnOutput(comments=[_comment("R-10", "realised")]),
        ]
    )

    report = await compose_netnew(
        _request(artifact),
        artifact,
        [ImageAnalysis(file="engine.jpg")],
        {"notes.txt": "Client supplied notes."},
        model=fake,
    )

    assert report.unverified == []
    assert report.attempts_used == 1
    assert len(report.ops) == 1
    assert report.ops[0].kind == "append"
    assert report.ops[0].requirement_id == "R-01"
    assert len(artifact.draft.sections[0].entries) == 2

    verdicts = {comment.requirement_id: comment.verdict for comment in report.comments}
    assert verdicts["R-01"] == "shortfall"
    assert verdicts["R-04"] == "shortfall"
    assert sum(verdict == "realised" for verdict in verdicts.values()) == 8
    assert all(
        comment.anchor.target_id
        in {entry.id for section in artifact.draft.sections for entry in section.entries}
        for comment in report.comments
    )


async def test_compose_netnew_validates_the_explicit_artifact() -> None:
    request_artifact = NetNewArtifact(
        job_id="job-1",
        form_id="form-1",
        draft=FormDraft(),
    )
    artifact = _artifact()
    fake = FakeLlm.script(
        [
            SliceTurnOutput(
                comments=[_comment(requirement.id, "realised") for requirement in REQUIREMENTS]
            )
        ]
    )

    report = await compose_netnew(
        _request(request_artifact),
        artifact,
        [],
        {},
        model=fake,
    )

    assert report.unverified == []
    assert len(report.comments) == len(REQUIREMENTS)


def test_scaffold_preserves_existing_entries_and_heading_order() -> None:
    artifact = NetNewArtifact(
        job_id="job-1",
        form_id="form-1",
        draft=FormDraft(
            sections=[
                Section(
                    id="section-04",
                    title="old title",
                    entries=[Entry(id="existing", order="m", value="keep", set_by="R-04")],
                )
            ]
        ),
    )
    from editor_service.flows.netnew import _ensure_scaffold

    _ensure_scaffold(artifact)

    assert [section.title for section in artifact.draft.sections] == [
        title for _section_id, title in SCAFFOLD_SECTIONS
    ]
    assert artifact.draft.sections[3].entries[0].id == "existing"
