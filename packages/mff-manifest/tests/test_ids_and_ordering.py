"""Ids are assigned after sorting by `(ordinal, text)` — never `ordinal` alone.

R-05/R-06 and R-08/R-09 each share both offset and span, so the `text` tiebreak is the
only thing that gives them a stable, reproducible order — tested directly here, on
exactly those two colliding pairs, independent of the full golden fixture test.
"""

from __future__ import annotations

from fakes import ScriptedExtractor
from golden import GOLDEN_REQUIREMENTS, RAW, unresolved

from mff_manifest import parse_manifest


async def test_ids_come_out_r01_through_r10_in_canonical_order() -> None:
    extractor = ScriptedExtractor(script=[unresolved()])
    manifest = await parse_manifest(RAW, extractor=extractor)

    assert [r.id for r in manifest.requirements] == [f"R-{i:02d}" for i in range(1, 11)]
    # And canonical order really is ordinal order (ties broken by text, asserted below).
    assert [r.ordinal for r in manifest.requirements] == sorted(
        r.ordinal for r in manifest.requirements
    )


async def test_tiebreak_windscreen_pair_r05_before_r06() -> None:
    # Same ordinal (84), same source_span. Only `text` distinguishes them, and "inside"
    # sorts before "outside" lexicographically — this pins that down explicitly rather
    # than relying on the golden test to notice if it ever stopped being true.
    r05, r06 = GOLDEN_REQUIREMENTS[4], GOLDEN_REQUIREMENTS[5]
    assert r05.ordinal == r06.ordinal
    assert r05.source_span == r06.source_span
    assert r05.text < r06.text

    # Feed the extractor the pair in the OPPOSITE order to what the tiebreak demands, so
    # the test fails if parse_manifest ever just preserved extractor order.
    reversed_pair = [
        r06.model_copy(update={"id": "R-00", "ordinal": -1}),
        r05.model_copy(update={"id": "R-00", "ordinal": -1}),
    ]
    manifest = await parse_manifest(RAW, extractor=ScriptedExtractor(script=[reversed_pair]))

    ids_by_text = {r.text: r.id for r in manifest.requirements}
    assert ids_by_text[r05.text] < ids_by_text[r06.text]


async def test_tiebreak_boot_pair_r08_before_r09() -> None:
    r08, r09 = GOLDEN_REQUIREMENTS[7], GOLDEN_REQUIREMENTS[8]
    assert r08.ordinal == r09.ordinal
    assert r08.source_span == r09.source_span
    assert r08.text < r09.text

    reversed_pair = [
        r09.model_copy(update={"id": "R-00", "ordinal": -1}),
        r08.model_copy(update={"id": "R-00", "ordinal": -1}),
    ]
    manifest = await parse_manifest(RAW, extractor=ScriptedExtractor(script=[reversed_pair]))

    ids_by_text = {r.text: r.id for r in manifest.requirements}
    assert ids_by_text[r08.text] < ids_by_text[r09.text]
