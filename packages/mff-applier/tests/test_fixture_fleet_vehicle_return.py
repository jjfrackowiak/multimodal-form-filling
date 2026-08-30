"""Applier tests built from the fleet-vehicle-return fixture — real data, not invented.

`SliceReport`s here carry the real `requirement_id`, `verdict`, `justification` and
`suggestion` values from `expected_output/review.yaml`, and the real R-01..R-10 `ordinal`s
from `expected_requirements.yaml`, chunked into slices the same way `Manifest.slices()`
does (max 6, taken in ordinal order — R-01..R-06 then R-07..R-10, a slice of six and a
slice of four). Only the anchor targets are synthetic: the real docx/entry ids are not
recoverable without parsing the actual document, which is out of scope here.

R-02 (four seat photographs) is the natural append case, so its four entries are built
from the real filenames `review.yaml` names as `satisfied_by` for R-02.
"""

from __future__ import annotations

from pathlib import Path

from mff_applier import apply_slice
from mff_contracts import (
    Anchor,
    Artifact,
    BlobRef,
    DerivativeArtifact,
    DraftOp,
    FormDraft,
    Manifest,
    NetNewArtifact,
    Node,
    Requirement,
    ReviewComment,
    Section,
    SliceReport,
)

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "fleet-vehicle-return"

SOURCE = BlobRef(
    uri="gs://bucket/jobs/j-1/source/abc",
    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes=2_800_000,
    sha256="formsupplied",
)

# expected_requirements.yaml: id -> ordinal, verbatim.
_ORDINALS = {
    "R-01": 11,
    "R-02": 22,
    "R-03": 34,
    "R-04": 56,
    "R-05": 84,
    "R-06": 84,
    "R-07": 120,
    "R-08": 135,
    "R-09": 135,
    "R-10": 178,
}


_MANIFEST_RAW = (FIXTURE / "manifest.txt").read_text(encoding="utf-8")


def _requirements() -> list[Requirement]:
    # source_span verbatim-in-raw is an invariant the parser asserts, not this model — a
    # single-character span keeps these requirements valid without re-deriving the parser's
    # actual spans, which is not this package's concern.
    return [
        Requirement(
            id=req_id, ordinal=ordinal, text=req_id, source_span=_MANIFEST_RAW[:1], source_line=1
        )
        for req_id, ordinal in _ORDINALS.items()
    ]


# review.yaml verdicts, verbatim (justification text abbreviated but not altered in meaning).
_REVIEW = {
    "R-01": (
        "fail",
        "Two engine-bay photographs were required; one was supplied.",
        "Supply a second photograph under the bonnet from a different angle.",
    ),
    "R-02": ("pass", "Four seat photographs supplied.", None),
    "R-03": ("pass", "Front three-quarter and rear three-quarter views supplied.", None),
    "R-04": (
        "fail",
        "Two headliner photographs were supplied, but only one meets the positional constraint.",
        "Retake the second headliner photograph with the camera positioned between the "
        "two front seats.",
    ),
    "R-05": ("pass", "Windscreen photographed from the cabin.", None),
    "R-06": ("pass", "Windscreen photographed from outside.", None),
    "R-07": ("pass", "Tyre tread photographed.", None),
    "R-08": ("pass", "Boot photographed with the tailgate open.", None),
    "R-09": ("pass", "Under-floor equipment photographed.", None),
    "R-10": ("pass", "Instrument cluster photographed; odometer legible at 59 650 km.", None),
}


def _comment(requirement_id: str) -> ReviewComment:
    verdict, justification, suggestion = _REVIEW[requirement_id]
    return ReviewComment(
        requirement_id=requirement_id,
        anchor=Anchor(kind="node", target_id=f"node-{requirement_id}"),
        verdict=verdict,
        justification=justification,
        suggestion=suggestion,
    )


def _derivative(artifact: Artifact) -> DerivativeArtifact:
    assert isinstance(artifact, DerivativeArtifact)
    return artifact


def test_manifest_slices_produce_a_slice_of_six_then_a_slice_of_four() -> None:
    manifest = Manifest(raw=_MANIFEST_RAW, requirements=_requirements())
    slices = manifest.slices()
    assert [s.requirement_ids for s in slices] == [
        ["R-01", "R-02", "R-03", "R-04", "R-05", "R-06"],
        ["R-07", "R-08", "R-09", "R-10"],
    ]


def test_two_sequential_slices_of_real_review_comments_accumulate_on_the_form() -> None:
    manifest = Manifest(raw=_MANIFEST_RAW, requirements=_requirements())
    slice_1, slice_2 = manifest.slices()

    artifact = DerivativeArtifact(
        form_id="form_supplied",
        source=SOURCE,
        nodes=[Node(id=f"node-R-{n:02d}", kind="paragraph", text="") for n in range(1, 11)],
    )

    report_1 = SliceReport(
        slice_id=slice_1.slice_id,
        comments=[_comment(r) for r in slice_1.requirement_ids],
        attempts_used=1,
    )
    result_1 = apply_slice(artifact, report_1, scope_ids=[])
    assert result_1.rejected == []

    report_2 = SliceReport(
        slice_id=slice_2.slice_id,
        comments=[_comment(r) for r in slice_2.requirement_ids],
        attempts_used=1,
    )
    result_2 = apply_slice(result_1.artifact, report_2, scope_ids=[])
    assert result_2.rejected == []

    final = _derivative(result_2.artifact)
    assert [c.requirement_id for c in final.comments] == [f"R-{n:02d}" for n in range(1, 11)]

    r01 = next(c for c in final.comments if c.requirement_id == "R-01")
    assert r01.verdict == "fail"
    assert r01.suggestion is not None  # req 16: a fail always carries a suggestion

    r04 = next(c for c in final.comments if c.requirement_id == "R-04")
    assert r04.verdict == "fail"  # the headline case: superficially met, substantively failed
    assert r04.suggestion is not None

    # The document's own nodes and the source blob never move — this is a derivative slice.
    assert final.nodes is artifact.nodes
    assert final.source is artifact.source


# review.yaml, R-02's satisfied_by — the four real filenames, unaltered.
_R02_PHOTOS = [
    "IMG_20260830_132755 (1).jpg",
    "IMG_20260830_132755.jpg",
    "IMG_20260830_132755 (2).jpg",
    "IMG_20260830_132755 (3).jpg",
]


def test_r02s_four_seat_photographs_are_built_by_four_appends() -> None:
    section = Section(id="seats", title="Fotele", entries=[])
    artifact = NetNewArtifact(form_id="WN-7020U", draft=FormDraft(sections=[section]))

    ops = [
        DraftOp(
            kind="append",
            requirement_id="R-02",
            section_id="seats",
            images=[
                BlobRef(
                    uri=f"gs://bucket/jobs/j-1/images/{i}",
                    content_type="image/jpeg",
                    size_bytes=1_000_000,
                    sha256=f"sha-{i}",
                )
            ],
        )
        for i, _photo in enumerate(_R02_PHOTOS)
    ]
    report = SliceReport(slice_id="slice-01", ops=ops, attempts_used=1)

    result = apply_slice(artifact, report, scope_ids=["seats"])

    assert isinstance(result.artifact, NetNewArtifact)
    entries = result.artifact.draft.sections[0].entries
    assert len(entries) == 4
    assert all(e.set_by == "R-02" for e in entries)
    assert len({e.id for e in entries}) == 4
    orders = [e.order for e in entries]
    assert orders == sorted(orders)
    assert result.overwrites == []
    assert result.rejected == []
