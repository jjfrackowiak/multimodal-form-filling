"""Property test: for any sequence of appends and inserts, entries read back in the
intended order and no pre-existing entry's `order` string changes.

No third-party property-testing library is added (the workspace does not carry one for
this package); this drives the same shape of check by hand across many random seeds,
exercising the real `apply_slice` append path — not just the ordering module in isolation.
"""

from __future__ import annotations

import random

from mff_applier import apply_slice, key_between
from mff_contracts import Artifact, DraftOp, FormDraft, NetNewArtifact, Section, SliceReport


def _report(op: DraftOp) -> SliceReport:
    return SliceReport(slice_id="slice-01", ops=[op], attempts_used=1)


def _net_new(artifact: Artifact) -> NetNewArtifact:
    """Narrow `ApplyResult.artifact` (a union) back to `NetNewArtifact` for assertions."""
    assert isinstance(artifact, NetNewArtifact)
    return artifact


def test_appends_never_change_a_pre_existing_entrys_order_string() -> None:
    rng = random.Random(1234)
    for trial in range(40):
        n = rng.randint(1, 60)
        artifact = NetNewArtifact(
            job_id="j-1",
            form_id="f",
            draft=FormDraft(sections=[Section(id="s", title="s", entries=[])]),
        )
        seen_ids: set[str] = set()
        for i in range(n):
            before = {e.id: e.order for e in artifact.draft.sections[0].entries}
            op = DraftOp(kind="append", requirement_id="R-01", section_id="s", value=str(i))
            result = apply_slice(artifact, _report(op), scope_ids=["s"])
            entries = _net_new(result.artifact).draft.sections[0].entries

            # Every previously-minted key is untouched, character for character.
            after = {e.id: e.order for e in entries}
            for entry_id, order in before.items():
                assert after[entry_id] == order, (
                    f"trial {trial}: appending entry {i} changed order of {entry_id!r}"
                )

            # The new entry is exactly one more than before, always sorts last, and its id
            # is fresh.
            assert len(entries) == len(before) + 1
            new_entry = entries[-1]
            assert new_entry.id not in seen_ids
            seen_ids.add(new_entry.id)
            if before:
                assert new_entry.order > max(before.values())

            # Reading the whole list back in `order` order reproduces insertion order.
            assert [e.value for e in sorted(entries, key=lambda e: e.order)] == [
                str(k) for k in range(i + 1)
            ]

            artifact = _net_new(result.artifact)


def test_arbitrary_inserts_between_siblings_never_disturb_neighbours() -> None:
    """Exercises `key_between` directly for insertion at an arbitrary position, not only
    append-after-last — the general case the applier's fractional ordering is built on."""
    rng = random.Random(99)
    for trial in range(40):
        keys: list[str] = [key_between(None, None)]
        for _ in range(rng.randint(1, 60)):
            pos = rng.randint(0, len(keys))
            lo = keys[pos - 1] if pos > 0 else None
            hi = keys[pos] if pos < len(keys) else None
            before = list(keys)
            new_key = key_between(lo, hi)
            keys.insert(pos, new_key)

            assert keys == sorted(keys), f"trial {trial}: keys not sorted after insert"
            assert len(set(keys)) == len(keys), f"trial {trial}: duplicate key minted"
            # every pre-existing key is byte-identical to before the insert
            remaining = [k for k in keys if k != new_key]
            assert remaining == before, f"trial {trial}: an existing key was renumbered"
