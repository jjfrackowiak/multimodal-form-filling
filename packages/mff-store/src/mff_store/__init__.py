"""mff-store — B12: implementations of the four repository Protocols B0 froze.

Two flavours of the same Protocols:

- `InMemory*` (`mff_store.memory`) — tests, evals, local dev, CI. Needs nothing.
- `Firestore*` / `Gcs*` (`mff_store.firestore_store`, `mff_store.gcs`) — GCP. Needs
  emulators locally, credentials in prod. Firestore holds shape (`Artifact`,
  `JobRecord`, `RequestRecord` JSON); GCS holds weight (every `.docx`, every image) —
  Firestore caps a document at 1 MiB, and the fixture's reviewed `.docx` alone is 2.8 MB.

`ArtifactRepository.save` takes the artifact *and* the cursor because they are written in
one transaction: as two writes, a crash between them either replays a slice (duplicate
comments) or skips one (silently missing requirements), both silently. See
`mff_store.memory.InMemoryArtifactRepository` and
`mff_store.firestore_store.FirestoreArtifactRepository`.
"""

from __future__ import annotations

from .errors import BlobNotFoundError, NotFoundError, VersionConflict
from .firestore_store import (
    FirestoreArtifactRepository,
    FirestoreJobRepository,
    FirestoreRequestRepository,
    make_firestore_client,
)
from .gcs import GcsBlobStore, make_gcs_client
from .memory import (
    InMemoryArtifactRepository,
    InMemoryBlobStore,
    InMemoryJobRepository,
    InMemoryRequestRepository,
)

__all__ = [
    "BlobNotFoundError",
    "FirestoreArtifactRepository",
    "FirestoreJobRepository",
    "FirestoreRequestRepository",
    "GcsBlobStore",
    "InMemoryArtifactRepository",
    "InMemoryBlobStore",
    "InMemoryJobRepository",
    "InMemoryRequestRepository",
    "NotFoundError",
    "VersionConflict",
    "make_firestore_client",
    "make_gcs_client",
]
