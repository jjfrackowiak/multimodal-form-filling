"""Completeness — the cross-slice half of req 16/17 that only the orchestrator can
check.

Every requirement in the manifest must carry at least one comment, across *all*
slices of a job, by the time the last slice has committed. No single slice run can
verify this — it only ever sees its own (at most six) requirements — which is exactly
why this check cannot live in the editor.

Not a second copy of the editor's per-requirement rules: it asks a question no slice
run is in a position to answer ("did every requirement get *a* verdict *somewhere*
across the whole job"), not whether any individual verdict was correct.
"""

from __future__ import annotations

from mff_contracts import Requirement, ReviewComment

__all__ = ["missing_requirement_ids"]


def missing_requirement_ids(
    requirements: list[Requirement], comments: list[ReviewComment]
) -> list[str]:
    """Requirement ids with no comment anywhere in `comments`, in requirement order."""
    covered = {comment.requirement_id for comment in comments}
    return [requirement.id for requirement in requirements if requirement.id not in covered]
