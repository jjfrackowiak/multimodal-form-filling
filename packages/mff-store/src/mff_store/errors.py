"""Errors shared by every adapter.

Both the in-memory and Firestore/GCS adapters raise these so callers (and tests) can
depend on one exception type regardless of which adapter is wired up.
"""

from __future__ import annotations

__all__ = ["BlobNotFoundError", "NotFoundError", "VersionConflict"]


class NotFoundError(LookupError):
    """Raised by `load`/`get` when nothing is stored under the given key."""


class BlobNotFoundError(LookupError):
    """Raised by `BlobStore.get` when the referenced object does not exist."""


class VersionConflict(RuntimeError):
    """Raised by `ArtifactRepository.save` when `expected_version` does not match.

    Slices run sequentially, so this should never fire in normal operation — it exists
    to catch a **duplicate runner**: the same job picked up twice after a crash. A
    conflict means something is wrong upstream; callers must not retry it away.
    """

    def __init__(self, key: str, expected: int, actual: int) -> None:
        self.key = key
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"version conflict for job {key!r}: expected {expected}, store has {actual}"
        )
