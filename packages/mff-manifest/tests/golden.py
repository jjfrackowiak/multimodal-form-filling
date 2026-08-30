"""The golden parse of `fixtures/fleet-vehicle-return/manifest.txt`, as Python.

Mirrors `fixtures/fleet-vehicle-return/expected_requirements.yaml` by hand rather than
parsing it at test time: the fixture is frozen and shared across many branches, and a
`Requirement`/`Constraint` object beats a yaml-dict round trip for the golden and live-eval
tests that need to construct or compare against real `mff_contracts` models. Keep this in
sync with the yaml if it ever changes.

Used by `test_golden_fixture.py` (what a correct extractor's output must canonicalise to)
and `test_live_eval.py` (what the real Gemma-backed extractor is scored against).
"""

from __future__ import annotations

from pathlib import Path

from mff_contracts import Constraint, Requirement

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "fleet-vehicle-return"
MANIFEST_PATH = FIXTURE_DIR / "manifest.txt"

RAW = MANIFEST_PATH.read_text(encoding="utf-8")

EXPECTED_TOTAL_PHOTOS = 16

# id/ordinal/source_line are the values `parse_manifest` computes deterministically from
# source_span; they are included so tests can assert the full object, not just the
# fields an extractor controls.
GOLDEN_REQUIREMENTS: list[Requirement] = [
    Requirement(
        id="R-01",
        ordinal=11,
        source_line=2,
        text="A photograph of the engine bay, taken with the bonnet open.",
        source_span="Pod maską",
        expected_count=2,
        ambiguity="repeated_verbatim_in_manifest",
    ),
    Requirement(
        id="R-02",
        ordinal=22,
        source_line=3,
        text="Four photographs of the seats.",
        source_span="4x fotele",
        expected_count=4,
    ),
    Requirement(
        id="R-03",
        ordinal=34,
        source_line=3,
        text="Two photographs of the vehicle taken on the diagonal.",
        source_span="2 przekatne pojazdu",
        expected_count=2,
    ),
    Requirement(
        id="R-04",
        ordinal=56,
        source_line=4,
        text=(
            "Two photographs of the headliner. Each must be taken from between the "
            "front seats."
        ),
        source_span="2x podsufitka",
        expected_count=2,
        constraint=Constraint(
            kind="camera_position",
            value="between_front_seats",
            source_span="Podsufitka trzeba spomiędzy forteli zrobić",
            source_line=10,
            note="'forteli' is a typo for 'foteli' (seats) in the client's original.",
        ),
    ),
    Requirement(
        id="R-05",
        ordinal=84,
        source_line=6,
        text="A photograph of the windscreen taken from inside the cabin.",
        source_span="Przednia szyba że środka i zewnątrz",
        expected_count=1,
    ),
    Requirement(
        id="R-06",
        ordinal=84,
        source_line=6,
        text="A photograph of the windscreen taken from outside the vehicle.",
        source_span="Przednia szyba że środka i zewnątrz",
        expected_count=1,
    ),
    Requirement(
        id="R-07",
        ordinal=120,
        source_line=7,
        text="A photograph of the tyre tread.",
        source_span="Bieżnik opony",
        expected_count=1,
    ),
    Requirement(
        id="R-08",
        ordinal=135,
        source_line=8,
        text="A photograph of the boot.",
        source_span="zdjęcie bagażnika + wyposażenia pod klapą",
        expected_count=1,
    ),
    Requirement(
        id="R-09",
        ordinal=135,
        source_line=8,
        text="A photograph of the equipment stowed under the boot lid/floor.",
        source_span="zdjęcie bagażnika + wyposażenia pod klapą",
        expected_count=1,
    ),
    Requirement(
        id="R-10",
        ordinal=178,
        source_line=9,
        text="A photograph of the instrument cluster.",
        source_span="i zegary",
        expected_count=1,
    ),
]

assert sum(r.expected_count for r in GOLDEN_REQUIREMENTS) == EXPECTED_TOTAL_PHOTOS
assert [r.id for r in GOLDEN_REQUIREMENTS] == [f"R-{i:02d}" for i in range(1, 11)]


def unresolved() -> list[Requirement]:
    """The same ten requirements as an extractor would hand back: real `id` unassigned
    (a placeholder — `parse_manifest` overwrites it), `ordinal`/`source_line` scrambled.

    Deliberately wrong on the fields `parse_manifest` recomputes, so a test asserting the
    output against `GOLDEN_REQUIREMENTS` only passes if the parser actually recomputed
    them rather than trusting a lucky extractor.
    """
    out = []
    for r in GOLDEN_REQUIREMENTS:
        updates: dict[str, object] = {"id": "R-00", "ordinal": -1, "source_line": -1}
        if r.constraint is not None:
            updates["constraint"] = r.constraint.model_copy(update={"source_line": -1})
        out.append(r.model_copy(update=updates))
    return out
