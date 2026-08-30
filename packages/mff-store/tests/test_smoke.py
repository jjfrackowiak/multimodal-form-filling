"""B12 is no longer an empty skeleton — proves the public surface imports cleanly."""

from __future__ import annotations

import mff_store


def test_package_exports_the_in_memory_adapters() -> None:
    assert set(mff_store.__all__) >= {
        "InMemoryArtifactRepository",
        "InMemoryBlobStore",
        "InMemoryJobRepository",
        "InMemoryRequestRepository",
        "VersionConflict",
        "NotFoundError",
        "BlobNotFoundError",
    }
