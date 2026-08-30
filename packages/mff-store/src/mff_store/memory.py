"""In-memory adapters — tests, evals, local dev, CI. Needs nothing.

Every method takes the same lock a real transactional backend would need, so the
concurrency behaviour under test here (version checks, atomic save) matches what the
Firestore adapter has to guarantee for real, not a simplification of it.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING

from mff_contracts import (
    Artifact,
    ArtifactRepository,
    BlobRef,
    BlobStore,
    JobCursor,
    JobRecord,
    JobRepository,
    RequestRecord,
    RequestRepository,
)

from .errors import BlobNotFoundError, NotFoundError, VersionConflict

__all__ = [
    "InMemoryArtifactRepository",
    "InMemoryBlobStore",
    "InMemoryJobRepository",
    "InMemoryRequestRepository",
]


class InMemoryArtifactRepository:
    """Keyed by `artifact.form_id`.

    `ArtifactRepository.save` (frozen) takes no `job_id` — the only identifying field on
    an `Artifact` is `form_id`. `load(job_id)` is therefore only correct when the caller's
    `job_id` and the artifact's `form_id` are the same string, which holds for the single
    form-per-job shape this repository is built against, but is not enforced by the type
    system. See the PR description for the gap this papers over.

    Storage is split into two dicts (`_artifacts`, `_cursors`) precisely so the "crash
    between the two writes" scenario is representable: `save` stages both, and rolls
    both back to their prior state if anything raises before the second write lands —
    the same guarantee a Firestore transaction gives for free.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._artifacts: dict[str, tuple[Artifact, int]] = {}
        self._cursors: dict[str, tuple[JobCursor, int]] = {}
        # Test seam only: when true, `save` raises after writing the artifact half but
        # before writing the cursor half, to prove the rollback actually rolls back.
        self.fail_before_cursor_write = False

    async def save(self, artifact: Artifact, cursor: JobCursor, *, expected_version: int) -> int:
        key = artifact.form_id
        async with self._lock:
            current = self._artifacts.get(key)
            actual_version = current[1] if current is not None else 0
            if actual_version != expected_version:
                raise VersionConflict(key, expected_version, actual_version)

            new_version = expected_version + 1
            prev_artifact = self._artifacts.get(key)
            prev_cursor = self._cursors.get(key)
            try:
                self._artifacts[key] = (artifact.model_copy(deep=True), new_version)
                if self.fail_before_cursor_write:
                    raise RuntimeError("simulated crash between artifact and cursor write")
                self._cursors[key] = (cursor.model_copy(deep=True), new_version)
            except Exception:
                if prev_artifact is None:
                    self._artifacts.pop(key, None)
                else:
                    self._artifacts[key] = prev_artifact
                if prev_cursor is None:
                    self._cursors.pop(key, None)
                else:
                    self._cursors[key] = prev_cursor
                raise
            return new_version

    async def load(self, job_id: str) -> tuple[Artifact, JobCursor, int]:
        async with self._lock:
            artifact_entry = self._artifacts.get(job_id)
            cursor_entry = self._cursors.get(job_id)
        if artifact_entry is None or cursor_entry is None:
            raise NotFoundError(f"no artifact for job_id={job_id!r}")
        artifact, artifact_version = artifact_entry
        cursor, _cursor_version = cursor_entry
        return artifact.model_copy(deep=True), cursor.model_copy(deep=True), artifact_version


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._records: dict[str, JobRecord] = {}

    async def put(self, record: JobRecord) -> None:
        async with self._lock:
            self._records[record.job_id] = record.model_copy(deep=True)

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            record = self._records.get(job_id)
        return record.model_copy(deep=True) if record is not None else None

    async def for_request(self, request_id: str) -> list[JobRecord]:
        async with self._lock:
            matches = [r for r in self._records.values() if r.request_id == request_id]
        return [r.model_copy(deep=True) for r in matches]


class InMemoryRequestRepository:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._records: dict[str, RequestRecord] = {}

    async def put(self, record: RequestRecord) -> None:
        async with self._lock:
            self._records[record.request_id] = record.model_copy(deep=True)

    async def get(self, request_id: str) -> RequestRecord | None:
        async with self._lock:
            record = self._records.get(request_id)
        return record.model_copy(deep=True) if record is not None else None


class InMemoryBlobStore:
    """Content-addressed by `sha256(data)`, exactly as `BlobStore.put` is scoped.

    `BlobStore.put` (frozen) carries no `job_id`, so addressing is global rather than
    per-job: identical bytes dedupe across the whole store, which is a superset of "dedupe
    within one job" and is what makes the fixture's 17-images-to-15-blobs case work.
    """

    def __init__(self, bucket: str = "mff-local") -> None:
        self._bucket = bucket
        self._lock = asyncio.Lock()
        self._objects: dict[str, bytes] = {}

    async def put(self, data: bytes, *, content_type: str, kind: str) -> BlobRef:
        sha256 = hashlib.sha256(data).hexdigest()
        uri = f"gs://{self._bucket}/{kind}/{sha256}"
        async with self._lock:
            # A retried job re-points at the existing object rather than writing a
            # second copy.
            if uri not in self._objects:
                self._objects[uri] = data
        return BlobRef(uri=uri, content_type=content_type, size_bytes=len(data), sha256=sha256)

    async def get(self, ref: BlobRef) -> bytes:
        async with self._lock:
            data = self._objects.get(ref.uri)
        if data is None:
            raise BlobNotFoundError(f"no blob at {ref.uri!r}")
        return data

    async def signed_url(self, ref: BlobRef, *, ttl_seconds: int) -> str:
        # No real signing to fake here; a stable, inspectable stand-in is enough for
        # callers that only need *a* URL back in tests.
        return f"{ref.uri}#ttl={ttl_seconds}"


if TYPE_CHECKING:  # pragma: no cover
    # Structural-conformance check against the frozen Protocols, enforced by mypy
    # --strict (not a runtime assertion — mff_contracts.repositories declares no
    # `@runtime_checkable`, so `isinstance` against these Protocols is not available).
    _artifact_repo: ArtifactRepository = InMemoryArtifactRepository()
    _job_repo: JobRepository = InMemoryJobRepository()
    _request_repo: RequestRepository = InMemoryRequestRepository()
    _blob_store: BlobStore = InMemoryBlobStore()
