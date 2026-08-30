"""ArtifactRepository — atomicity is the point of this branch.

Runs against every adapter in `conftest.ADAPTERS` via the `artifact_repo` fixture. A test
that only passed against the in-memory adapter would mean the Firestore adapter is
untested and the Protocol bought nothing — see CONTEXT.md.
"""

from __future__ import annotations

import pytest
from factories import make_artifact, make_cursor

from mff_store.errors import NotFoundError, VersionConflict


async def test_save_then_load_round_trips(artifact_repo: object) -> None:
    artifact = make_artifact("job-1")
    cursor = make_cursor(0)

    version = await artifact_repo.save(artifact, cursor, expected_version=0)  # type: ignore[attr-defined]
    assert version == 1

    loaded_artifact, loaded_cursor, loaded_version = await artifact_repo.load("job-1")  # type: ignore[attr-defined]
    assert loaded_artifact.form_id == "job-1"
    assert loaded_cursor.slice_index == 0
    assert loaded_version == 1


async def test_sequential_slices_advance_the_version(artifact_repo: object) -> None:
    artifact = make_artifact("job-2")
    v1 = await artifact_repo.save(artifact, make_cursor(0), expected_version=0)  # type: ignore[attr-defined]
    assert v1 == 1

    # Slice 2 sees what slice 1 committed and advances the cursor in the same write.
    v2 = await artifact_repo.save(artifact, make_cursor(1), expected_version=1)  # type: ignore[attr-defined]
    assert v2 == 2

    _artifact, cursor, version = await artifact_repo.load("job-2")  # type: ignore[attr-defined]
    assert cursor.slice_index == 1
    assert version == 2


async def test_load_missing_job_raises_not_found(artifact_repo: object) -> None:
    with pytest.raises(NotFoundError):
        await artifact_repo.load("no-such-job")  # type: ignore[attr-defined]


async def test_version_conflict_raises_rather_than_retrying(artifact_repo: object) -> None:
    """`expected_version` exists to catch a duplicate runner, not to arbitrate normal
    operation — a conflict must raise immediately, with no retry loop built around it."""
    artifact = make_artifact("job-3")
    await artifact_repo.save(artifact, make_cursor(0), expected_version=0)  # type: ignore[attr-defined]

    # A second runner replaying the same slice believes the version is still 0.
    with pytest.raises(VersionConflict) as exc_info:
        await artifact_repo.save(artifact, make_cursor(0), expected_version=0)  # type: ignore[attr-defined]
    assert exc_info.value.expected == 0
    assert exc_info.value.actual == 1

    # The conflicting write must not have landed.
    _artifact, cursor, version = await artifact_repo.load("job-3")  # type: ignore[attr-defined]
    assert version == 1
    assert cursor.slice_index == 0


async def test_crash_between_artifact_and_cursor_write_leaves_neither(
    artifact_repo: object,
) -> None:
    """The whole point of the branch: `save` is one transaction, not two writes.

    A crash between committing the artifact and advancing the cursor must leave neither
    landed — not the artifact alone (which would silently skip a slice on retry) and not
    the cursor alone (which would silently replay one).
    """
    artifact = make_artifact("job-4")
    artifact_repo.fail_before_cursor_write = True  # type: ignore[attr-defined]  # test seam
    try:
        with pytest.raises(Exception):  # noqa: B017 — the injected fault, adapter-specific
            await artifact_repo.save(artifact, make_cursor(0), expected_version=0)  # type: ignore[attr-defined]
    finally:
        artifact_repo.fail_before_cursor_write = False  # type: ignore[attr-defined]

    with pytest.raises(NotFoundError):
        await artifact_repo.load("job-4")  # type: ignore[attr-defined]

    # And the store is left clean enough for a normal save to succeed afterwards —
    # nothing was left half-written that would poison a retry.
    version = await artifact_repo.save(artifact, make_cursor(0), expected_version=0)  # type: ignore[attr-defined]
    assert version == 1


async def test_crash_on_a_later_slice_rolls_back_to_the_prior_slice(
    artifact_repo: object,
) -> None:
    """Same fault, but on slice 2+ of a job that already has a committed slice 1 — the
    rollback must restore the prior (slice 1) state, not wipe the job entirely."""
    artifact = make_artifact("job-5")
    v1 = await artifact_repo.save(artifact, make_cursor(0), expected_version=0)  # type: ignore[attr-defined]
    assert v1 == 1

    artifact_repo.fail_before_cursor_write = True  # type: ignore[attr-defined]  # test seam
    try:
        with pytest.raises(Exception):  # noqa: B017 — the injected fault, adapter-specific
            await artifact_repo.save(artifact, make_cursor(1), expected_version=1)  # type: ignore[attr-defined]
    finally:
        artifact_repo.fail_before_cursor_write = False  # type: ignore[attr-defined]

    _artifact, cursor, version = await artifact_repo.load("job-5")  # type: ignore[attr-defined]
    assert version == 1
    assert cursor.slice_index == 0
