"""Validators for Anchor and ReviewComment (req 10, 16)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mff_contracts import Anchor, ReviewComment


def _comment(**overrides: object) -> ReviewComment:
    defaults: dict[str, object] = {
        "requirement_id": "R-01",
        "anchor": Anchor(kind="node", target_id="n-1"),
        "verdict": "pass",
        "justification": "The engine bay photograph is present and clear.",
        "suggestion": None,
    }
    defaults.update(overrides)
    return ReviewComment(**defaults)


# --- suggestion required iff verdict == "fail" ------------------------------------------


def test_fail_with_suggestion_is_valid() -> None:
    comment = _comment(verdict="fail", suggestion="Add the missing photograph.")
    assert comment.verdict == "fail"
    assert comment.suggestion == "Add the missing photograph."


def test_fail_without_suggestion_is_rejected() -> None:
    with pytest.raises(ValidationError, match="suggestion is required"):
        _comment(verdict="fail", suggestion=None)


def test_pass_without_suggestion_is_valid() -> None:
    comment = _comment(verdict="pass", suggestion=None)
    assert comment.suggestion is None


def test_pass_with_suggestion_is_rejected() -> None:
    with pytest.raises(ValidationError, match="suggestion must be empty"):
        _comment(verdict="pass", suggestion="Not needed.")


@pytest.mark.parametrize("verdict", ["realised", "shortfall", "not_applicable", "unverified"])
def test_non_fail_verdicts_reject_a_suggestion(verdict: str) -> None:
    with pytest.raises(ValidationError, match="suggestion must be empty"):
        _comment(verdict=verdict, suggestion="should not be here")


# --- justification is non-empty on every comment (req 16) ------------------------------


def test_non_empty_justification_is_valid() -> None:
    comment = _comment(justification="A clear reason.")
    assert comment.justification == "A clear reason."


def test_empty_justification_is_rejected() -> None:
    with pytest.raises(ValidationError, match="justification must not be empty"):
        _comment(justification="")


def test_whitespace_only_justification_is_rejected() -> None:
    with pytest.raises(ValidationError, match="justification must not be empty"):
        _comment(justification="   \n\t")


# --- Anchor.target_id is set unless kind == "document" ---------------------------------


def test_node_anchor_requires_target_id() -> None:
    anchor = Anchor(kind="node", target_id="n-42")
    assert anchor.target_id == "n-42"


def test_node_anchor_without_target_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="requires target_id"):
        Anchor(kind="node", target_id=None)


def test_entry_anchor_without_target_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="requires target_id"):
        Anchor(kind="entry")


def test_document_anchor_needs_no_target_id() -> None:
    anchor = Anchor(kind="document")
    assert anchor.target_id is None


def test_document_anchor_with_target_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not set target_id"):
        Anchor(kind="document", target_id="n-1")


def test_unverified_may_anchor_to_the_document() -> None:
    """`Anchor` gives `unverified` somewhere to live when no target was ever identified."""
    comment = _comment(
        anchor=Anchor(kind="document"),
        verdict="unverified",
        justification="Retries exhausted before a target could be identified.",
    )
    assert comment.anchor.kind == "document"
    assert comment.anchor.target_id is None
