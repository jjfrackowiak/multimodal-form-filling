"""Synthetic cases for `Manifest.slices()`, independent of the fixture.

Slicing is plain chunking: sort by `ordinal`, take consecutive groups of at most 6. There
is no minimum — the last chunk is whatever is left over, including a chunk of one.
"""

from __future__ import annotations

from mff_contracts import Manifest, Requirement

_MAX_SLICE_SIZE = 6


def _req(id_: str, ordinal: int) -> Requirement:
    return Requirement(
        id=id_,
        ordinal=ordinal,
        text=f"requirement {id_}",
        source_span=id_,
        source_line=1,
    )


def test_ten_requirements_chunk_into_six_and_four() -> None:
    reqs = [_req(f"R-{i:02d}", ordinal=i * 10) for i in range(1, 11)]
    manifest = Manifest(raw="n/a", requirements=reqs)

    plans = manifest.slices()

    assert [len(p.requirement_ids) for p in plans] == [6, 4]
    assert sum(len(p.requirement_ids) for p in plans) == 10
    for plan in plans:
        assert len(plan.requirement_ids) <= _MAX_SLICE_SIZE
    # each chunk preserves ordinal order
    for plan in plans:
        ordinals = [int(rid.split("-")[1]) * 10 for rid in plan.requirement_ids]
        assert ordinals == sorted(ordinals)


def test_exactly_six_requirements_yield_one_full_slice() -> None:
    reqs = [_req(f"R-{i:02d}", ordinal=i * 10) for i in range(1, 7)]
    manifest = Manifest(raw="n/a", requirements=reqs)
    plans = manifest.slices()
    assert len(plans) == 1
    assert len(plans[0].requirement_ids) == 6


def test_seven_requirements_yield_a_trailing_slice_of_one() -> None:
    """No minimum any more: the last chunk is whatever is left over."""
    reqs = [_req(f"R-{i:02d}", ordinal=i * 10) for i in range(1, 8)]
    manifest = Manifest(raw="n/a", requirements=reqs)
    plans = manifest.slices()
    assert [len(p.requirement_ids) for p in plans] == [6, 1]


def test_a_manifest_with_no_requirements_slices_to_nothing() -> None:
    manifest = Manifest(raw="n/a", requirements=[])
    assert manifest.slices() == []


def test_a_single_requirement_yields_one_slice_of_one() -> None:
    manifest = Manifest(raw="n/a", requirements=[_req("R-01", 5)])
    plans = manifest.slices()
    assert len(plans) == 1
    assert plans[0].requirement_ids == ["R-01"]


def test_chunking_respects_ordinal_order_not_input_order() -> None:
    reqs = [_req("R-03", 30), _req("R-01", 10), _req("R-02", 20)]
    manifest = Manifest(raw="n/a", requirements=reqs)
    plans = manifest.slices()
    assert plans[0].requirement_ids == ["R-01", "R-02", "R-03"]
