"""Shared fixture-data loaders for the delivery test suite.

Golden data comes straight from `fixtures/fleet-vehicle-return/expected_requirements.yaml`
and `expected_output/review.yaml` — not reproduced by hand — mirroring the pattern in
`packages/mff-contracts/tests/test_manifest_slices.py`. If either fixture drifts, these
tests fail rather than silently drifting with it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mff_contracts import Anchor, Constraint, Requirement, ReviewComment


def _find_fixture_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "fixtures" / "fleet-vehicle-return"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("fixtures/fleet-vehicle-return not found above this test file")


FIXTURE = _find_fixture_root()


def _build_constraint(entry: dict[str, object]) -> Constraint | None:
    raw = entry.get("constraint")
    if raw is None:
        return None
    assert isinstance(raw, dict)
    return Constraint(
        kind=raw["kind"],
        value=raw["value"],
        source_span=raw["constraint_source_span"],
        source_line=raw["constraint_source_line"],
        note=raw.get("note"),
    )


def load_manifest_text() -> str:
    return (FIXTURE / "manifest.txt").read_text(encoding="utf-8")


def load_requirements() -> list[Requirement]:
    data = yaml.safe_load((FIXTURE / "expected_requirements.yaml").read_text(encoding="utf-8"))
    requirements = []
    for entry in data["requirements"]:
        requirements.append(
            Requirement(
                id=entry["id"],
                ordinal=entry["ordinal"],
                text=entry["text"],
                source_span=entry["source_span"],
                source_line=entry["source_line"],
                expected_count=entry.get("expected_count", 1),
                constraint=_build_constraint(entry),
                ambiguity=entry.get("ambiguity"),
            )
        )
    return requirements


def load_review_comments() -> list[ReviewComment]:
    """Build the fixture's 10 `ReviewComment`s from `expected_output/review.yaml`.

    Anchor is irrelevant to delivery (it is a comment-in-the-document concern, B6/B7's),
    so every comment gets a stand-in `node` anchor here — `deliver()` never looks at it.
    """
    data = yaml.safe_load((FIXTURE / "expected_output" / "review.yaml").read_text(encoding="utf-8"))
    comments = []
    for entry in data["verdicts"]:
        comments.append(
            ReviewComment(
                requirement_id=entry["requirement_id"],
                anchor=Anchor(kind="node", target_id=f"node-{entry['requirement_id']}"),
                verdict=entry["verdict"],
                justification=entry["justification"].strip(),
                suggestion=entry.get("suggestion", "").strip() or None,
            )
        )
    return comments


@pytest.fixture
def fixture_requirements() -> list[Requirement]:
    return load_requirements()


@pytest.fixture
def fixture_comments() -> list[ReviewComment]:
    return load_review_comments()


@pytest.fixture
def fixture_manifest_text() -> str:
    return load_manifest_text()
