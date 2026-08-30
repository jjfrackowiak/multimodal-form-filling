"""Net-new artifacts (req 14, req 15): DraftOp semantics, scope, and the D3 overwrite signal."""

from __future__ import annotations

from mff_applier import apply_slice
from mff_contracts import (
    Anchor,
    Artifact,
    BlobRef,
    DraftOp,
    Entry,
    FormDraft,
    NetNewArtifact,
    ReviewComment,
    Section,
    SliceReport,
)

BLOB = BlobRef(uri="gs://b/x.jpg", content_type="image/jpeg", size_bytes=100, sha256="x")
BLOB_2 = BlobRef(uri="gs://b/y.jpg", content_type="image/jpeg", size_bytes=200, sha256="y")


def _artifact(sections: list[Section]) -> NetNewArtifact:
    return NetNewArtifact(job_id="j-1", form_id="WN-7020U", draft=FormDraft(sections=sections))


def _draft(artifact: Artifact) -> FormDraft:
    """Narrow `ApplyResult.artifact` (a union) back to its draft for net-new assertions."""
    assert isinstance(artifact, NetNewArtifact)
    return artifact.draft


def _report(ops: list[DraftOp], comments: list[ReviewComment] | None = None) -> SliceReport:
    return SliceReport(slice_id="slice-01", ops=ops, comments=comments or [], attempts_used=1)


# --------------------------------------------------------------------------- append


def test_append_mints_a_fresh_entry_after_the_last_one_in_scope() -> None:
    existing = Entry(id="e-1", order="a0", value="front-left seat", set_by="R-02")
    section = Section(id="seats", title="Seats", entries=[existing])
    artifact = _artifact([section])
    op = DraftOp(kind="append", requirement_id="R-02", section_id="seats", value="front-right seat")

    result = apply_slice(artifact, _report([op]), scope_ids=["seats"])

    entries = _draft(result.artifact).sections[0].entries
    assert len(entries) == 2
    assert entries[0].id == "e-1"
    assert entries[0].order == "a0"  # untouched
    minted = entries[1]
    assert minted.id != "e-1"
    assert minted.order > "a0"
    assert minted.value == "front-right seat"
    assert minted.set_by == "R-02"
    assert result.overwrites == []
    assert result.rejected == []


def test_append_into_an_empty_section_mints_the_first_order_key() -> None:
    section = Section(id="seats", title="Seats", entries=[])
    artifact = _artifact([section])
    op = DraftOp(kind="append", requirement_id="R-02", section_id="seats", value="seat")

    result = apply_slice(artifact, _report([op]), scope_ids=["seats"])

    entries = _draft(result.artifact).sections[0].entries
    assert len(entries) == 1
    assert entries[0].value == "seat"


def test_four_appends_build_r02s_four_seat_entries_in_order() -> None:
    # R-02 wants four seat entries — this is the fixture's natural append test.
    section = Section(id="seats", title="Seats", entries=[])
    artifact = _artifact([section])
    labels = ["front-left", "front-right", "rear-left", "rear-right"]
    ops = [
        DraftOp(kind="append", requirement_id="R-02", section_id="seats", value=label)
        for label in labels
    ]

    result = apply_slice(artifact, _report(ops), scope_ids=["seats"])

    entries = _draft(result.artifact).sections[0].entries
    assert [e.value for e in entries] == labels
    orders = [e.order for e in entries]
    assert orders == sorted(orders)
    assert len(set(orders)) == 4
    assert len({e.id for e in entries}) == 4


def test_append_with_images_stores_them_on_the_new_entry() -> None:
    section = Section(id="seats", title="Seats", entries=[])
    artifact = _artifact([section])
    op = DraftOp(kind="append", requirement_id="R-02", section_id="seats", images=[BLOB, BLOB_2])

    result = apply_slice(artifact, _report([op]), scope_ids=["seats"])

    assert _draft(result.artifact).sections[0].entries[0].images == [BLOB, BLOB_2]


def test_append_outside_scope_is_rejected_not_applied() -> None:
    section = Section(id="seats", title="Seats", entries=[])
    artifact = _artifact([section])
    op = DraftOp(kind="append", requirement_id="R-02", section_id="seats", value="seat")

    result = apply_slice(artifact, _report([op]), scope_ids=["other-section"])

    assert _draft(result.artifact).sections[0].entries == []
    assert len(result.rejected) == 1
    assert result.rejected[0].op == op
    assert "outside scope_ids" in result.rejected[0].reason


def test_append_to_unknown_section_is_rejected() -> None:
    artifact = _artifact([Section(id="seats", title="Seats", entries=[])])
    op = DraftOp(kind="append", requirement_id="R-02", section_id="ghost", value="x")

    result = apply_slice(artifact, _report([op]), scope_ids=["ghost"])

    assert len(result.rejected) == 1
    assert "unknown section" in result.rejected[0].reason


# --------------------------------------------------------------------------- set


def test_set_replaces_value_and_images_without_changing_id_or_order() -> None:
    entry = Entry(id="e-1", order="a0", value="old value", set_by="R-01")
    section = Section(id="engine-bay", title="Engine bay", entries=[entry])
    artifact = _artifact([section])
    op = DraftOp(
        kind="set", requirement_id="R-01", entry_id="e-1", value="new value", images=[BLOB]
    )

    result = apply_slice(artifact, _report([op]), scope_ids=["engine-bay"])

    updated = _draft(result.artifact).sections[0].entries[0]
    assert updated.id == "e-1"
    assert updated.order == "a0"
    assert updated.value == "new value"
    assert updated.images == [BLOB]
    assert updated.set_by == "R-01"
    assert result.overwrites == []  # same requirement re-setting its own entry


def test_set_with_only_value_leaves_images_untouched() -> None:
    entry = Entry(id="e-1", order="a0", value="old", images=[BLOB], set_by="R-01")
    artifact = _artifact([Section(id="s", title="s", entries=[entry])])
    op = DraftOp(kind="set", requirement_id="R-01", entry_id="e-1", value="new")

    result = apply_slice(artifact, _report([op]), scope_ids=["s"])

    updated = _draft(result.artifact).sections[0].entries[0]
    assert updated.value == "new"
    assert updated.images == [BLOB]


def test_original_artifact_is_never_mutated_by_a_set() -> None:
    entry = Entry(id="e-1", order="a0", value="old", set_by="R-01")
    artifact = _artifact([Section(id="s", title="s", entries=[entry])])
    op = DraftOp(kind="set", requirement_id="R-01", entry_id="e-1", value="new")

    apply_slice(artifact, _report([op]), scope_ids=["s"])

    assert artifact.draft.sections[0].entries[0].value == "old"


def test_set_on_unknown_entry_is_rejected() -> None:
    artifact = _artifact([Section(id="s", title="s", entries=[])])
    op = DraftOp(kind="set", requirement_id="R-01", entry_id="ghost", value="x")

    result = apply_slice(artifact, _report([op]), scope_ids=["s"])

    assert len(result.rejected) == 1
    assert "unknown entry" in result.rejected[0].reason


def test_set_outside_scope_is_rejected_not_applied() -> None:
    entry = Entry(id="e-1", order="a0", value="old", set_by="R-01")
    artifact = _artifact([Section(id="s", title="s", entries=[entry])])
    op = DraftOp(kind="set", requirement_id="R-01", entry_id="e-1", value="new")

    result = apply_slice(artifact, _report([op]), scope_ids=["other"])

    assert _draft(result.artifact).sections[0].entries[0].value == "old"
    assert "outside scope_ids" in result.rejected[0].reason


# --------------------------------------------------------------------------- delete


def test_delete_removes_the_entry() -> None:
    entry = Entry(id="e-1", order="a0", value="x", set_by="R-01")
    artifact = _artifact([Section(id="s", title="s", entries=[entry])])
    op = DraftOp(kind="delete", requirement_id="R-01", entry_id="e-1")

    result = apply_slice(artifact, _report([op]), scope_ids=["s"])

    assert _draft(result.artifact).sections[0].entries == []
    assert result.rejected == []


def test_delete_on_unknown_entry_is_rejected() -> None:
    artifact = _artifact([Section(id="s", title="s", entries=[])])
    op = DraftOp(kind="delete", requirement_id="R-01", entry_id="ghost")

    result = apply_slice(artifact, _report([op]), scope_ids=["s"])

    assert "unknown entry" in result.rejected[0].reason


def test_delete_outside_scope_is_rejected_not_applied() -> None:
    entry = Entry(id="e-1", order="a0", value="x", set_by="R-01")
    artifact = _artifact([Section(id="s", title="s", entries=[entry])])
    op = DraftOp(kind="delete", requirement_id="R-01", entry_id="e-1")

    result = apply_slice(artifact, _report([op]), scope_ids=["other"])

    assert len(_draft(result.artifact).sections[0].entries) == 1
    assert "outside scope_ids" in result.rejected[0].reason


def test_deleting_a_comment_anchored_entry_is_refused_and_names_the_comment() -> None:
    entry = Entry(id="e-1", order="a0", value="headliner shot", set_by="R-04")
    artifact = NetNewArtifact(
        job_id="j-1",
        form_id="WN-7020U",
        draft=FormDraft(sections=[Section(id="s", title="s", entries=[entry])]),
        comments=[
            ReviewComment(
                requirement_id="R-04",
                anchor=Anchor(kind="entry", target_id="e-1"),
                verdict="shortfall",
                justification="Not shot from between the front seats.",
            )
        ],
    )
    op = DraftOp(kind="delete", requirement_id="R-09", entry_id="e-1")

    result = apply_slice(artifact, _report([op]), scope_ids=["s"])

    assert _draft(result.artifact).sections[0].entries == [entry]  # not deleted
    assert result.overwrites == []  # refused before any mutation is considered
    assert len(result.rejected) == 1
    assert "R-04" in result.rejected[0].reason
    assert "e-1" in result.rejected[0].reason


def test_deleting_an_entry_anchored_by_a_comment_in_the_same_report_is_also_refused() -> None:
    entry = Entry(id="e-1", order="a0", value="x", set_by="R-04")
    artifact = _artifact([Section(id="s", title="s", entries=[entry])])
    comment = ReviewComment(
        requirement_id="R-04",
        anchor=Anchor(kind="entry", target_id="e-1"),
        verdict="realised",
        justification="Present.",
    )
    op = DraftOp(kind="delete", requirement_id="R-09", entry_id="e-1")

    result = apply_slice(artifact, _report([op], comments=[comment]), scope_ids=["s"])

    assert _draft(result.artifact).sections[0].entries == [entry]
    assert len(result.rejected) == 1


def test_deleting_an_entry_with_no_anchored_comment_succeeds() -> None:
    entry = Entry(id="e-1", order="a0", value="x", set_by="R-04")
    artifact = NetNewArtifact(
        job_id="j-1",
        form_id="WN-7020U",
        draft=FormDraft(sections=[Section(id="s", title="s", entries=[entry])]),
        comments=[
            ReviewComment(
                requirement_id="R-05",
                anchor=Anchor(kind="entry", target_id="some-other-entry"),
                verdict="realised",
                justification="Unrelated entry.",
            )
        ],
    )
    op = DraftOp(kind="delete", requirement_id="R-09", entry_id="e-1")

    result = apply_slice(artifact, _report([op]), scope_ids=["s"])

    assert _draft(result.artifact).sections[0].entries == []
    assert result.rejected == []


def test_document_level_comments_do_not_protect_any_entry() -> None:
    entry = Entry(id="e-1", order="a0", value="x", set_by="R-04")
    artifact = NetNewArtifact(
        job_id="j-1",
        form_id="WN-7020U",
        draft=FormDraft(sections=[Section(id="s", title="s", entries=[entry])]),
        comments=[
            ReviewComment(
                requirement_id="R-17",
                anchor=Anchor(kind="document"),
                verdict="unverified",
                justification="Could not be checked automatically.",
            )
        ],
    )
    op = DraftOp(kind="delete", requirement_id="R-09", entry_id="e-1")

    result = apply_slice(artifact, _report([op]), scope_ids=["s"])

    assert _draft(result.artifact).sections[0].entries == []
    assert result.rejected == []


# --------------------------------------------------------------------------- overwrite (D3)


def test_set_by_a_different_requirement_records_an_overwrite_but_still_applies() -> None:
    entry = Entry(id="e-1", order="a0", value="old", set_by="R-01")
    artifact = _artifact([Section(id="s", title="s", entries=[entry])])
    op = DraftOp(kind="set", requirement_id="R-05", entry_id="e-1", value="new")

    result = apply_slice(artifact, _report([op]), scope_ids=["s"])

    assert _draft(result.artifact).sections[0].entries[0].value == "new"  # not blocked
    assert _draft(result.artifact).sections[0].entries[0].set_by == "R-05"  # ownership moves
    assert len(result.overwrites) == 1
    overwrite = result.overwrites[0]
    assert overwrite.entry_id == "e-1"
    assert overwrite.previous_requirement == "R-01"
    assert overwrite.new_requirement == "R-05"


def test_delete_by_a_different_requirement_records_an_overwrite_and_still_deletes() -> None:
    entry = Entry(id="e-1", order="a0", value="old", set_by="R-01")
    artifact = _artifact([Section(id="s", title="s", entries=[entry])])
    op = DraftOp(kind="delete", requirement_id="R-05", entry_id="e-1")

    result = apply_slice(artifact, _report([op]), scope_ids=["s"])

    assert _draft(result.artifact).sections[0].entries == []
    assert len(result.overwrites) == 1
    assert result.overwrites[0].entry_id == "e-1"
    assert result.overwrites[0].previous_requirement == "R-01"
    assert result.overwrites[0].new_requirement == "R-05"


def test_second_set_by_the_same_requirement_that_wrote_it_is_not_an_overwrite() -> None:
    entry = Entry(id="e-1", order="a0", value="old", set_by="R-01")
    artifact = _artifact([Section(id="s", title="s", entries=[entry])])
    op = DraftOp(kind="set", requirement_id="R-01", entry_id="e-1", value="revised")

    result = apply_slice(artifact, _report([op]), scope_ids=["s"])

    assert result.overwrites == []


def test_overwrite_ownership_updates_so_a_third_requirement_sees_the_second_as_prior() -> None:
    entry = Entry(id="e-1", order="a0", value="v0", set_by="R-01")
    artifact = _artifact([Section(id="s", title="s", entries=[entry])])
    first = apply_slice(
        artifact,
        _report([DraftOp(kind="set", requirement_id="R-02", entry_id="e-1", value="v1")]),
        scope_ids=["s"],
    )
    second = apply_slice(
        first.artifact,
        _report([DraftOp(kind="set", requirement_id="R-03", entry_id="e-1", value="v2")]),
        scope_ids=["s"],
    )
    assert first.overwrites[0].previous_requirement == "R-01"
    assert first.overwrites[0].new_requirement == "R-02"
    assert second.overwrites[0].previous_requirement == "R-02"  # not R-01 — ownership moved
    assert second.overwrites[0].new_requirement == "R-03"


# --------------------------------------------------------------------------- comments (net-new)


def test_comments_are_appended_alongside_ops_in_the_same_report() -> None:
    section = Section(id="s", title="s", entries=[])
    artifact = _artifact([section])
    op = DraftOp(kind="append", requirement_id="R-02", section_id="s", value="seat")
    comment = ReviewComment(
        requirement_id="R-02",
        anchor=Anchor(kind="document"),
        verdict="realised",
        justification="Four seats present.",
    )

    result = apply_slice(artifact, _report([op], comments=[comment]), scope_ids=["s"])

    assert len(_draft(result.artifact).sections[0].entries) == 1
    assert result.artifact.comments == [comment]
    assert artifact.comments == []
