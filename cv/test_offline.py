"""No Vertex. Hash + checklist completeness."""

from __future__ import annotations

from pathlib import Path

from cv.checklist import load_checklist, spans_complete
from cv.images import collapse_duplicates, list_images

ROOT = Path(__file__).resolve().parents[1]


def test_fleet_spans() -> None:
    c = load_checklist(ROOT / "fixtures/fleet-vehicle-return/expected_requirements.yaml")
    assert len(c.requirements) == 10
    assert spans_complete(c)
    assert c.requirements[3].id == "R-04"
    assert c.requirements[3].constraint == "between_front_seats"


def test_fleet_dupes() -> None:
    folder = ROOT / "fixtures/fleet-vehicle-return/images"
    files = list_images(folder)
    unique, pairs = collapse_duplicates(files)
    assert len(files) == 17
    assert len(unique) == 15
    assert len(pairs) == 2


if __name__ == "__main__":
    test_fleet_spans()
    test_fleet_dupes()
    print("offline ok")
