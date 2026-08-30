"""Repositories — the seam that keeps GCP out of CI.

Protocols only — no implementations. Store adapters (Firestore, GCS, in-memory fakes) are
other branches' work (B-store); this package defines only the shape they must satisfy.
"""

from __future__ import annotations

from typing import Protocol

from .artifacts import Artifact
from .blobs import BlobRef
from .jobs import JobCursor, JobRecord, RequestRecord

__all__ = ["ArtifactRepository", "BlobStore", "JobRepository", "RequestRepository"]


class ArtifactRepository(Protocol):
    async def save(self, artifact: Artifact, cursor: JobCursor, *, expected_version: int) -> int:
        """Persist `artifact` at `artifact.job_id`, the key `load` later reads by."""
        ...

    async def load(self, job_id: str) -> tuple[Artifact, JobCursor, int]: ...


class JobRepository(Protocol):
    async def put(self, record: JobRecord) -> None: ...

    async def get(self, job_id: str) -> JobRecord | None: ...

    async def for_request(self, request_id: str) -> list[JobRecord]: ...  # the barrier


class RequestRepository(Protocol):
    async def put(self, record: RequestRecord) -> None: ...

    async def get(self, request_id: str) -> RequestRecord | None: ...


class BlobStore(Protocol):
    async def put(self, data: bytes, *, content_type: str, kind: str) -> BlobRef: ...

    async def get(self, ref: BlobRef) -> bytes: ...

    async def signed_url(self, ref: BlobRef, *, ttl_seconds: int) -> str: ...
