"""Completeness validation — on Python objects, deterministic, never the model judging
itself (see the B8 brief).

Two checks, both structural:

1. Every `pending` requirement id has exactly one `ReviewComment` in the turn's output.
   `justification` non-empty and `suggestion` required-iff-`fail` are already enforced by
   `ReviewComment`'s own pydantic validators, so this module does not repeat them.
2. Every non-`document` anchor's `target_id` actually resolves against `artifact` — a node
   id for `DerivativeArtifact`, an entry id for `NetNewArtifact`.

`validate` only ever looks at comments for ids in `pending`: a comment for an id that has
already settled (or was never asked about) is silently ignored. That is what makes rule 2
("a settled answer is never revisited") hold — see `run.run_slice`, which narrows `pending`
after every attempt, and `tests/llm/test_run_slice.py::test_settled_answer_never_revisited`.
"""

from __future__ import annotations

from editor_service.llm.output import SliceTurnOutput
from mff_contracts import Anchor, Artifact, DerivativeArtifact, ReviewComment

__all__ = ["validate"]


def validate(
    output: SliceTurnOutput,
    pending: list[str],
    artifact: Artifact,
) -> tuple[dict[str, ReviewComment], dict[str, str]]:
    """Split `pending` into settled comments and per-id validation errors.

    Returns `(passed, errors)`. Every id in `pending` appears in exactly one of the two
    dicts — `passed` for a requirement this turn answered completely, `errors` for one it
    did not (with a human-readable reason to feed back into `prompts.retry_prompt`).
    """
    by_id = {
        comment.requirement_id: comment
        for comment in output.comments
        if comment.requirement_id in pending
    }
    passed: dict[str, ReviewComment] = {}
    errors: dict[str, str] = {}

    for requirement_id in pending:
        comment = by_id.get(requirement_id)
        if comment is None:
            errors[requirement_id] = f"no comment was returned for requirement {requirement_id}"
            continue
        anchor_error = _anchor_error(comment.anchor, artifact)
        if anchor_error is not None:
            errors[requirement_id] = anchor_error
            continue
        passed[requirement_id] = comment

    return passed, errors


def _anchor_error(anchor: Anchor, artifact: Artifact) -> str | None:
    if anchor.kind == "document":
        return None
    target_id = anchor.target_id
    known_ids = _known_anchor_ids(artifact)
    if target_id not in known_ids:
        return (
            f"anchor target_id {target_id!r} (kind={anchor.kind!r}) does not resolve "
            "against the artifact"
        )
    return None


def _known_anchor_ids(artifact: Artifact) -> set[str]:
    if isinstance(artifact, DerivativeArtifact):
        return {node.id for node in artifact.nodes}
    return {entry.id for section in artifact.draft.sections for entry in section.entries}
