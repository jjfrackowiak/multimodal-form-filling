"""Shared net-new section/entry skeleton.

The editor used to scaffold this only in-process. The email orchestrator compiled the
unseeded artifact (one empty section), so `set_field` ops never landed and Word got a
job-id title. Both sides must start from the same draft.
"""

from __future__ import annotations

from mff_contracts import Entry, FormDraft, Requirement, Section

__all__ = ["SCAFFOLD_SECTIONS", "netnew_scaffold"]

SCAFFOLD_SECTIONS: tuple[tuple[str, str], ...] = (
    ("section-01", "1. Under the bonnet"),
    ("section-02", "2. Seats"),
    ("section-03", "3. Vehicle diagonals"),
    ("section-04", "4. Headliner"),
    ("section-05", "5. Windscreen"),
    ("section-06", "6. Tyre tread"),
    ("section-07", "7. Boot and equipment"),
    ("section-08", "8. Gauges"),
    ("section-09", "9. Notes"),
)

_REQUIREMENT_SECTIONS = (
    "section-01",
    "section-02",
    "section-03",
    "section-04",
    "section-05",
    "section-05",
    "section-06",
    "section-07",
    "section-07",
    "section-08",
)


def netnew_scaffold(requirements: list[Requirement] | None = None) -> FormDraft:
    sections = [Section(id=section_id, title=title) for section_id, title in SCAFFOLD_SECTIONS]
    by_id = {section.id: section for section in sections}
    for index, requirement in enumerate(requirements or []):
        entry_id = f"entry-{requirement.id}"
        section_id = _REQUIREMENT_SECTIONS[min(index, len(_REQUIREMENT_SECTIONS) - 1)]
        by_id[section_id].entries.append(
            Entry(id=entry_id, order=f"slot-{index + 1:02d}", set_by=requirement.id)
        )
    return FormDraft(sections=sections)
