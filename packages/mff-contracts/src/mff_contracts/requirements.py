"""Manifest and requirements — reqs 4, 5, 11.

`Requirement` is the atomic, individually-checkable unit parsed from a client's manifest.
`Manifest` bundles the raw text with the parsed requirements and owns the one piece of
derived structure every consumer must build the same way: how requirements group into
slices for review.

Invariants asserted elsewhere (by the parser, not this package): every `source_span`
appears verbatim in `Manifest.raw`, and `id` is assigned after sorting by
`(ordinal, text)` — `text` breaks the tie when two requirements share a span.

`SlicePlan` lives here, next to `Manifest.slices()`, rather than alongside
`SliceRequest`/`SliceReport` in `slices.py` — it has no dependency on those and keeping it
here avoids a circular import (`slices.py` needs `Requirement`).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["Constraint", "Manifest", "Requirement", "SlicePlan"]

# Slicing is plain chunking: sort by ordinal, take consecutive groups of at most this
# many. Any grouping by content (e.g. by a `scope`-like key) is a guess about which
# requirements belong together, and a wrong guess costs a whole slice run to discover.
# Chunking in the client's own order is predictable, trivially testable, and has no model
# output anywhere in its path. There is no minimum: the last chunk is whatever is left
# over, including a chunk of one.
_MAX_SLICE_SIZE = 6


class Constraint(BaseModel):
    """A qualifier on a requirement — what makes a supplied item count as satisfying it.

    Structured rather than a formatted string: the consumer needs `value` to decide a
    verdict, and a string forces every producer to invent an encoding and every consumer
    to parse it back.
    """

    kind: str  # "camera_position"
    value: str  # "between_front_seats" — decides the verdict; never lose this
    source_span: str  # VERBATIM substring of Manifest.raw, like Requirement.source_span
    source_line: int  # 1-indexed
    note: str | None = None


class Requirement(BaseModel):
    """One normalised, individually checkable statement extracted from a manifest."""

    id: str  # "R-03", assigned AFTER canonical sort so ids read in order
    ordinal: int  # Manifest.raw.index(source_span) — the ordering key
    text: str  # one normalised, individually checkable statement
    source_span: str  # VERBATIM substring of Manifest.raw
    source_line: int  # 1-indexed, for the delivered requirement list
    applies_to: list[str] = Field(default_factory=list)  # form ids; empty = all forms
    expected_count: int = 1  # "4x seats" is ONE requirement with count 4
    constraint: Constraint | None = None
    ambiguity: str | None = None  # recorded, never silently resolved


class SlicePlan(BaseModel):
    """The execution unit a slice runs against: a bounded group of requirements."""

    slice_id: str
    ordinal: int  # min(r.ordinal) — execution order, computed
    requirement_ids: list[str]  # at most 6 per slice, taken in ordinal order


class Manifest(BaseModel):
    """The parsed manifest: raw text plus the requirements extracted from it."""

    raw: str  # the client's text, byte-for-byte
    requirements: list[Requirement]  # in canonical (ordinal) order

    def slices(self) -> list[SlicePlan]:
        """Sort requirements by `ordinal` ascending, then chunk into groups of at most
        `_MAX_SLICE_SIZE`, taken consecutively. That is the entire algorithm."""
        ordered = sorted(self.requirements, key=lambda r: (r.ordinal, r.text))
        chunks = [
            ordered[start : start + _MAX_SLICE_SIZE]
            for start in range(0, len(ordered), _MAX_SLICE_SIZE)
        ]
        return [
            SlicePlan(
                slice_id=f"slice-{index:02d}",
                ordinal=chunk[0].ordinal,
                requirement_ids=[r.id for r in chunk],
            )
            for index, chunk in enumerate(chunks, start=1)
        ]
