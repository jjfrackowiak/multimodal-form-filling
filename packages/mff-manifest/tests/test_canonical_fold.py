"""Deterministic canonicalise: totals are not requirements; repeated phrases fold."""

from __future__ import annotations

from fakes import ScriptedExtractor
from golden import RAW, unresolved

from mff_contracts import Requirement
from mff_manifest import parse_manifest


def _req(**over: object) -> Requirement:
    base: dict[str, object] = {
        "id": "R-00",
        "ordinal": -1,
        "source_line": -1,
        "text": "placeholder",
        "source_span": "Under the bonnet",
        "expected_count": 1,
    }
    base.update(over)
    return Requirement(**base)


async def test_total_photo_count_is_not_a_requirement() -> None:
    extra = _req(
        text="The form must contain 16 photos.",
        source_span="16 photos,",
        expected_count=16,
    )
    extractor = ScriptedExtractor(script=[[extra, *unresolved()]])
    manifest = await parse_manifest(RAW, extractor=extractor)
    assert len(manifest.requirements) == 10
    assert all("16 photo" not in r.source_span for r in manifest.requirements)
    assert manifest.requirements[0].id == "R-01"
    assert manifest.requirements[0].source_span == "Under the bonnet"


async def test_repeated_bonnet_lines_fold_to_count_two() -> None:
    first = _req(
        text="A photo of the area under the bonnet must be included.",
        source_span="Under the bonnet",
        expected_count=1,
    )
    second = _req(
        text="A photo of the area under the bonnet must be included.",
        source_span="Under the bonnet",
        expected_count=1,
    )
    rest = [r for r in unresolved() if r.source_span != "Under the bonnet"]
    extractor = ScriptedExtractor(script=[[first, second, *rest]])
    manifest = await parse_manifest(RAW, extractor=extractor)
    bonnet = [r for r in manifest.requirements if r.source_span == "Under the bonnet"]
    assert len(bonnet) == 1
    assert bonnet[0].expected_count == 2
    assert bonnet[0].ambiguity == "repeated_verbatim_in_manifest"
    assert bonnet[0].id == "R-01"
    assert len(manifest.requirements) == 10


async def test_one_line_two_subjects_is_not_folded() -> None:
    extractor = ScriptedExtractor(script=[unresolved()])
    manifest = await parse_manifest(RAW, extractor=extractor)
    windscreen = [r for r in manifest.requirements if r.source_span.startswith("Windscreen")]
    boot = [r for r in manifest.requirements if r.source_span.startswith("boot photo")]
    assert len(windscreen) == 2
    assert len(boot) == 2


async def test_stranded_camera_position_is_folded_onto_matching_requirement() -> None:
    headliner = _req(
        text="There must be 2 photos of the headliner.",
        source_span="2x headliner",
        expected_count=2,
    )
    stranded_constraint = _req(
        text="The headliner must be taken from between the seats.",
        source_span="Headliner must be taken from between the seats",
    )
    rest = [r for r in unresolved() if r.source_span != "2x headliner"]
    extractor = ScriptedExtractor(script=[[headliner, *rest, stranded_constraint]])

    manifest = await parse_manifest(RAW, extractor=extractor)

    assert len(manifest.requirements) == 10
    parsed_headliner = next(r for r in manifest.requirements if r.source_span == "2x headliner")
    assert parsed_headliner.constraint is not None
    assert parsed_headliner.constraint.kind == "camera_position"
    assert parsed_headliner.constraint.value == "between_front_seats"
    assert (
        parsed_headliner.constraint.source_span == "Headliner must be taken from between the seats"
    )
    assert parsed_headliner.constraint.source_line == 10


async def test_camera_position_rule_without_matching_subject_is_retained() -> None:
    standalone = _req(
        text="The dashboard must be taken from between the seats.",
        source_span="Headliner must be taken from between the seats",
    )
    extractor = ScriptedExtractor(script=[[standalone]])

    manifest = await parse_manifest(RAW, extractor=extractor)

    assert manifest.requirements == [
        standalone.model_copy(update={"ordinal": 200, "source_line": 10, "id": "R-01"})
    ]
