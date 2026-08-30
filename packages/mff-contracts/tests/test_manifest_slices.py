"""`Manifest.slices()` against the fleet fixture's 10 requirements.

Golden data comes straight from `expected_requirements.yaml` and
`expected_output/structure.yaml` in the fixture — not reproduced by hand — so this test
fails the moment either drifts from the models it exercises.

Slicing is plain chunking: sorted by ordinal, taken in consecutive groups of at most 6.
The fleet fixture's 10 requirements therefore produce exactly two slices: 6 and 4.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mff_contracts import Constraint, Manifest, Requirement

_MAX_SLICE_SIZE = 6


def _find_fixture_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "fixtures" / "fleet-vehicle-return"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("fixtures/fleet-vehicle-return not found above this test file")


FIXTURE = _find_fixture_root()


def _build_constraint(entry: dict[str, object]) -> Constraint | None:
    """Build a real `Constraint` from the fixture's structured block.

    The fixture describes a constraint as five fields (`kind`, `value`,
    `constraint_source_span`, `constraint_source_line`, `note`). Flattening this to
    `constraint["kind"]` — as an earlier version of this test did — discards `value`,
    which is the part that actually decides R-04's verdict. Build the real model instead.
    """
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


def _load_requirements() -> list[Requirement]:
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


def _expected_ordinals() -> dict[str, int]:
    structure = yaml.safe_load(
        (FIXTURE / "expected_output" / "structure.yaml").read_text(encoding="utf-8")
    )
    return dict(structure["common"]["expected_ordinals"])


@pytest.fixture
def manifest() -> Manifest:
    raw = (FIXTURE / "manifest.txt").read_text(encoding="utf-8")
    return Manifest(raw=raw, requirements=_load_requirements())


def test_requirement_ordinals_match_the_fixtures_expected_ordinals(manifest: Manifest) -> None:
    expected = _expected_ordinals()
    assert {r.id: r.ordinal for r in manifest.requirements} == expected


def test_ten_requirements_chunk_into_exactly_two_slices_of_six_and_four(
    manifest: Manifest,
) -> None:
    plans = manifest.slices()
    assert [len(p.requirement_ids) for p in plans] == [6, 4]
    assert plans[0].requirement_ids == [f"R-{i:02d}" for i in range(1, 7)]
    assert plans[1].requirement_ids == [f"R-{i:02d}" for i in range(7, 11)]


def test_slices_cover_every_requirement_exactly_once(manifest: Manifest) -> None:
    plans = manifest.slices()
    seen = [rid for plan in plans for rid in plan.requirement_ids]
    assert sorted(seen) == sorted(r.id for r in manifest.requirements)
    assert len(seen) == len(set(seen))  # no requirement appears in two slices


def test_no_slice_exceeds_six_requirements(manifest: Manifest) -> None:
    plans = manifest.slices()
    assert len(plans) > 0
    for plan in plans:
        assert len(plan.requirement_ids) <= _MAX_SLICE_SIZE, plan


def test_slice_ordinal_is_the_minimum_of_its_requirements(manifest: Manifest) -> None:
    by_id = {r.id: r for r in manifest.requirements}
    for plan in manifest.slices():
        assert plan.ordinal == min(by_id[rid].ordinal for rid in plan.requirement_ids)


def test_slices_are_sorted_ascending_by_ordinal(manifest: Manifest) -> None:
    ordinals = [plan.ordinal for plan in manifest.slices()]
    assert ordinals == sorted(ordinals)


def test_slicing_is_deterministic(manifest: Manifest) -> None:
    first = [p.requirement_ids for p in manifest.slices()]
    second = [p.requirement_ids for p in manifest.slices()]
    assert first == second


def test_r04_constraint_value_decides_the_verdict_without_parsing_a_string(
    manifest: Manifest,
) -> None:
    """The regression this change exists to prevent: R-04's constraint, built exactly as
    `expected_requirements.yaml` describes it, must expose `value` as a real attribute —
    not something a consumer has to parse back out of a flattened string."""
    by_id = {r.id: r for r in manifest.requirements}
    r04 = by_id["R-04"]
    assert r04.constraint is not None
    assert isinstance(r04.constraint, Constraint)
    assert r04.constraint.kind == "camera_position"
    assert r04.constraint.value == "between_front_seats"
    assert r04.constraint.note is not None
    assert "later line" in r04.constraint.note


def test_r04_constraint_source_span_is_verbatim_in_the_manifest_and_survives_utf8(
    manifest: Manifest,
) -> None:
    """The constraint arrives on manifest line 10, six lines after the item it
    qualifies. Its `source_span` must be a byte-for-byte substring of `Manifest.raw`."""
    by_id = {r.id: r for r in manifest.requirements}
    constraint = by_id["R-04"].constraint
    assert constraint is not None
    assert constraint.source_span == "Headliner must be taken from between the seats"
    assert constraint.source_span in manifest.raw
    assert constraint.source_line == 10
    # UTF-8 round-trips through model construction and JSON.
    restored = Constraint.model_validate_json(constraint.model_dump_json())
    assert restored.source_span == constraint.source_span
    assert "between the seats" in restored.source_span
