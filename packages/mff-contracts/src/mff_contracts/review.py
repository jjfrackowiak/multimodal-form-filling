"""Review — reqs 10, 16, 17.

Every comment is anchored inline, in both modes: a review comment not attached to the
content it judges is a footnote, and req 10 asks for one comment per requirement *on the
form*. `kind="document"` is the only exception, reserved for `unverified`, where the agent
may never have identified a target — often that is precisely why it failed.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, model_validator

__all__ = ["Anchor", "ReviewComment"]


class Anchor(BaseModel):
    """Where a comment attaches. `target_id` is set unless `kind == "document"` — an
    unanchored comment cannot exist in OOXML."""

    kind: Literal["node", "entry", "document"]
    target_id: str | None = None  # None only when kind == "document"

    @model_validator(mode="after")
    def _target_id_matches_kind(self) -> Self:
        if self.kind == "document":
            if self.target_id is not None:
                raise ValueError("Anchor(kind='document') must not set target_id")
        elif not self.target_id:
            raise ValueError(f"Anchor(kind={self.kind!r}) requires target_id")
        return self


class ReviewComment(BaseModel):
    """One requirement's verdict, anchored to the content it judges.

    Comments cite requirement **numbers**, not verbatim quotes: the parsed requirement
    list (with `text` and `source_span`) ships with the delivery, stated once rather than
    repeated in every comment.
    """

    requirement_id: str  # referenced by NUMBER; the text ships with delivery
    anchor: Anchor
    verdict: Literal[
        "pass",
        "fail",  # derivative
        "realised",
        "shortfall",  # net-new
        "not_applicable",  # genuinely does not apply
        "unverified",  # req 17 terminal
    ]
    justification: str  # req 16: never empty
    suggestion: str | None = None  # required iff verdict == "fail"

    @model_validator(mode="after")
    def _justification_is_non_empty(self) -> Self:
        if not self.justification.strip():
            raise ValueError("ReviewComment.justification must not be empty (req 16)")
        return self

    @model_validator(mode="after")
    def _suggestion_required_iff_fail(self) -> Self:
        has_suggestion = bool(self.suggestion and self.suggestion.strip())
        if self.verdict == "fail" and not has_suggestion:
            raise ValueError("ReviewComment.suggestion is required when verdict == 'fail'")
        if self.verdict != "fail" and has_suggestion:
            raise ValueError("ReviewComment.suggestion must be empty unless verdict == 'fail'")
        return self
