"""`apply_slice` — the one place a validated `SliceReport` becomes changes to an `Artifact`.

Pure: `(Artifact, SliceReport, scope_ids) -> ApplyResult`. No I/O, no model, no async.
Every mode's correctness (req 14: surgical, no full regeneration; req 15: output tools
apply the edits) funnels through this function.
"""

from __future__ import annotations

import uuid
from typing import Any

from mff_contracts import (
    Artifact,
    DerivativeArtifact,
    DraftOp,
    Entry,
    FormDraft,
    NetNewArtifact,
    ReviewComment,
    Section,
    SliceReport,
)

from .models import ApplyResult, Overwrite, Rejection
from .ordering import key_after

__all__ = ["apply_slice"]


def apply_slice(artifact: Artifact, report: SliceReport, scope_ids: list[str]) -> ApplyResult:
    if isinstance(artifact, DerivativeArtifact):
        return _apply_derivative(artifact, report)
    return _apply_net_new(artifact, report, scope_ids)


def _apply_derivative(artifact: DerivativeArtifact, report: SliceReport) -> ApplyResult:
    if report.ops:
        # A derivative artifact has no draft to apply ops to (req 14: the client's document
        # is never modified). A non-empty `ops` here is a bug in the caller, not something
        # to apply partially or silently drop — refuse the whole report and say why.
        rejected = [
            Rejection(
                reason=(
                    "derivative artifacts are never mutated: SliceReport.ops must be "
                    "empty for a derivative slice; this report was rejected in full"
                ),
                op=op,
            )
            for op in report.ops
        ]
        return ApplyResult(artifact=artifact, overwrites=[], rejected=rejected)

    updated = artifact.model_copy(update={"comments": [*artifact.comments, *report.comments]})
    return ApplyResult(artifact=updated, overwrites=[], rejected=[])


def _apply_net_new(
    artifact: NetNewArtifact, report: SliceReport, scope_ids: list[str]
) -> ApplyResult:
    scope = set(scope_ids)
    draft = artifact.draft.model_copy(deep=True)
    protected = _anchored_entries(artifact.comments)
    for entry_id, comments in _anchored_entries(report.comments).items():
        protected.setdefault(entry_id, []).extend(comments)

    overwrites: list[Overwrite] = []
    rejected: list[Rejection] = []

    for op in report.ops:
        if op.kind == "append":
            _apply_append(draft, op, scope, rejected)
        elif op.kind == "set":
            _apply_set(draft, op, scope, overwrites, rejected)
        else:
            _apply_delete(draft, op, scope, protected, overwrites, rejected)

    updated = artifact.model_copy(
        update={"draft": draft, "comments": [*artifact.comments, *report.comments]}
    )
    return ApplyResult(artifact=updated, overwrites=overwrites, rejected=rejected)


def _anchored_entries(comments: list[ReviewComment]) -> dict[str, list[ReviewComment]]:
    """Map entry id -> the comments anchored to it (`kind == "entry"` only)."""
    protected: dict[str, list[ReviewComment]] = {}
    for comment in comments:
        if comment.anchor.kind == "entry" and comment.anchor.target_id is not None:
            protected.setdefault(comment.anchor.target_id, []).append(comment)
    return protected


def _find_section(draft: FormDraft, section_id: str) -> Section | None:
    for section in draft.sections:
        if section.id == section_id:
            return section
    return None


def _find_entry(draft: FormDraft, entry_id: str) -> tuple[Section, int] | None:
    for section in draft.sections:
        for index, entry in enumerate(section.entries):
            if entry.id == entry_id:
                return section, index
    return None


def _apply_append(
    draft: FormDraft, op: DraftOp, scope: set[str], rejected: list[Rejection]
) -> None:
    section_id = op.section_id
    assert section_id is not None  # guaranteed by DraftOp's own model_validator

    if section_id not in scope:
        rejected.append(
            Rejection(
                reason=f"append targets section {section_id!r}, outside scope_ids",
                op=op,
            )
        )
        return

    section = _find_section(draft, section_id)
    if section is None:
        rejected.append(Rejection(reason=f"append targets unknown section {section_id!r}", op=op))
        return

    last_order = section.entries[-1].order if section.entries else None
    section.entries.append(
        Entry(
            id=f"entry-{uuid.uuid4().hex}",
            order=key_after(last_order),
            value=op.value,
            images=list(op.images),
            set_by=op.requirement_id,
        )
    )


def _apply_set(
    draft: FormDraft,
    op: DraftOp,
    scope: set[str],
    overwrites: list[Overwrite],
    rejected: list[Rejection],
) -> None:
    entry_id = op.entry_id
    assert entry_id is not None  # guaranteed by DraftOp's own model_validator

    found = _find_entry(draft, entry_id)
    if found is None:
        rejected.append(Rejection(reason=f"set targets unknown entry {entry_id!r}", op=op))
        return

    section, index = found
    if section.id not in scope:
        rejected.append(
            Rejection(
                reason=(
                    f"set targets entry {entry_id!r} in section {section.id!r}, outside scope_ids"
                ),
                op=op,
            )
        )
        return

    entry = section.entries[index]
    _record_overwrite_if_any(entry, op, overwrites)

    updates: dict[str, Any] = {"set_by": op.requirement_id}
    if op.value is not None:
        updates["value"] = op.value
    if op.images:
        updates["images"] = list(op.images)
    section.entries[index] = entry.model_copy(update=updates)


def _apply_delete(
    draft: FormDraft,
    op: DraftOp,
    scope: set[str],
    protected: dict[str, list[ReviewComment]],
    overwrites: list[Overwrite],
    rejected: list[Rejection],
) -> None:
    entry_id = op.entry_id
    assert entry_id is not None  # guaranteed by DraftOp's own model_validator

    found = _find_entry(draft, entry_id)
    if found is None:
        rejected.append(Rejection(reason=f"delete targets unknown entry {entry_id!r}", op=op))
        return

    section, index = found
    if section.id not in scope:
        rejected.append(
            Rejection(
                reason=(
                    f"delete targets entry {entry_id!r} in section {section.id!r}, "
                    "outside scope_ids"
                ),
                op=op,
            )
        )
        return

    entry = section.entries[index]
    anchoring = protected.get(entry.id)
    if anchoring:
        names = ", ".join(sorted({c.requirement_id for c in anchoring}))
        rejected.append(
            Rejection(
                reason=(
                    f"delete of entry {entry.id!r} refused: a review comment for "
                    f"requirement(s) {names} is anchored to it"
                ),
                op=op,
            )
        )
        return

    _record_overwrite_if_any(entry, op, overwrites)
    del section.entries[index]


def _record_overwrite_if_any(entry: Entry, op: DraftOp, overwrites: list[Overwrite]) -> None:
    if entry.set_by != op.requirement_id:
        overwrites.append(
            Overwrite(
                entry_id=entry.id,
                previous_requirement=entry.set_by,
                new_requirement=op.requirement_id,
            )
        )
