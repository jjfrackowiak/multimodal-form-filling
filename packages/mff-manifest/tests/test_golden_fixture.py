"""The golden test: `expected_requirements.yaml`, as `golden.GOLDEN_REQUIREMENTS`.

Scripts an extractor to return the ten real fields (text, source_span, expected_count,
constraint, ambiguity) with everything `parse_manifest` recomputes deliberately wrong
(`golden.unresolved()`), then asserts the parser's output matches the golden data exactly.
That is the only way this test can tell "the parser recomputed ordinal/source_line/id
correctly" apart from "the extractor happened to get them right".
"""

from __future__ import annotations

from fakes import ScriptedExtractor
from golden import GOLDEN_REQUIREMENTS, RAW, unresolved

from mff_manifest import parse_manifest


async def test_golden_parse_matches_expected_requirements_yaml() -> None:
    extractor = ScriptedExtractor(script=[unresolved()])
    manifest = await parse_manifest(RAW, extractor=extractor)

    assert manifest.raw == RAW
    assert manifest.requirements == GOLDEN_REQUIREMENTS


async def test_golden_parse_field_by_field() -> None:
    """Same assertion, unrolled per requirement — a regression here should name exactly
    which requirement and which field broke, not just "list != list"."""
    extractor = ScriptedExtractor(script=[unresolved()])
    manifest = await parse_manifest(RAW, extractor=extractor)

    by_id = {r.id: r for r in manifest.requirements}
    assert set(by_id) == {f"R-{i:02d}" for i in range(1, 11)}

    for expected in GOLDEN_REQUIREMENTS:
        actual = by_id[expected.id]
        assert actual.ordinal == expected.ordinal, expected.id
        assert actual.source_line == expected.source_line, expected.id
        assert actual.text == expected.text, expected.id
        assert actual.source_span == expected.source_span, expected.id
        assert actual.expected_count == expected.expected_count, expected.id
        assert actual.constraint == expected.constraint, expected.id
        assert actual.ambiguity == expected.ambiguity, expected.id


async def test_r04_constraint_value_survives() -> None:
    """The one field the brief singles out: `value` is what decides whether R-04 passes."""
    extractor = ScriptedExtractor(script=[unresolved()])
    manifest = await parse_manifest(RAW, extractor=extractor)

    r04 = next(r for r in manifest.requirements if r.id == "R-04")
    assert r04.constraint is not None
    assert r04.constraint.kind == "camera_position"
    assert r04.constraint.value == "between_front_seats"
    assert r04.constraint.source_line == 10


async def test_ambiguity_is_recorded_not_resolved_away() -> None:
    extractor = ScriptedExtractor(script=[unresolved()])
    manifest = await parse_manifest(RAW, extractor=extractor)

    r01 = next(r for r in manifest.requirements if r.id == "R-01")
    assert r01.ambiguity == "repeated_verbatim_in_manifest"
    assert r01.expected_count == 2

    # No other requirement carries an ambiguity — this is a genuinely singular case.
    assert [r.id for r in manifest.requirements if r.ambiguity is not None] == ["R-01"]


async def test_expected_count_is_not_repetition() -> None:
    extractor = ScriptedExtractor(script=[unresolved()])
    manifest = await parse_manifest(RAW, extractor=extractor)

    # "4x fotele" is ONE requirement with expected_count 4, never four requirements.
    seat_requirements = [r for r in manifest.requirements if r.source_span == "4x fotele"]
    assert len(seat_requirements) == 1
    assert seat_requirements[0].expected_count == 4


async def test_one_line_two_requirements() -> None:
    extractor = ScriptedExtractor(script=[unresolved()])
    manifest = await parse_manifest(RAW, extractor=extractor)

    windscreen = [r for r in manifest.requirements if r.source_span.startswith("Przednia")]
    boot = [r for r in manifest.requirements if r.source_span.startswith("zdjęcie bagażnika")]
    assert {r.id for r in windscreen} == {"R-05", "R-06"}
    assert {r.id for r in boot} == {"R-08", "R-09"}


async def test_manifest_slices_gives_two_slices_of_six_and_four() -> None:
    extractor = ScriptedExtractor(script=[unresolved()])
    manifest = await parse_manifest(RAW, extractor=extractor)

    slices = manifest.slices()
    assert [len(s.requirement_ids) for s in slices] == [6, 4]
    assert slices[0].requirement_ids == [f"R-{i:02d}" for i in range(1, 7)]
    assert slices[1].requirement_ids == [f"R-{i:02d}" for i in range(7, 11)]
