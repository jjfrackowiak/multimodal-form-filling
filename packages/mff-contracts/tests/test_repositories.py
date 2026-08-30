"""Repositories are Protocols only — no implementations here. This proves the shape is
implementable and usable by a fake, which is exactly what B-store's real tests will do."""

from __future__ import annotations

from mff_contracts import (
    Artifact,
    ArtifactRepository,
    BlobRef,
    BlobStore,
    DerivativeArtifact,
    JobCursor,
    JobRecord,
    JobRepository,
    RequestRecord,
    RequestRepository,
)

SOURCE = BlobRef(
    uri="gs://bucket/jobs/j-1/source/abc",
    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes=1024,
    sha256="abc123",
)


class InMemoryArtifactRepository:
    def __init__(self) -> None:
        self._store: dict[str, tuple[Artifact, JobCursor, int]] = {}

    async def save(self, artifact: Artifact, cursor: JobCursor, *, expected_version: int) -> int:
        job_id = artifact.job_id
        current = self._store[job_id][2] if job_id in self._store else 0
        if current != expected_version:
            raise ValueError("version conflict")
        new_version = current + 1
        self._store[job_id] = (artifact, cursor, new_version)
        return new_version

    async def load(self, job_id: str) -> tuple[Artifact, JobCursor, int]:
        return self._store[job_id]


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._records: dict[str, JobRecord] = {}

    async def put(self, record: JobRecord) -> None:
        self._records[record.job_id] = record

    async def get(self, job_id: str) -> JobRecord | None:
        return self._records.get(job_id)

    async def for_request(self, request_id: str) -> list[JobRecord]:
        return [r for r in self._records.values() if r.request_id == request_id]


class InMemoryRequestRepository:
    def __init__(self) -> None:
        self._records: dict[str, RequestRecord] = {}

    async def put(self, record: RequestRecord) -> None:
        self._records[record.request_id] = record

    async def get(self, request_id: str) -> RequestRecord | None:
        return self._records.get(request_id)


class InMemoryBlobStore:
    async def put(self, data: bytes, *, content_type: str, kind: str) -> BlobRef:
        import hashlib

        digest = hashlib.sha256(data).hexdigest()
        return BlobRef(
            uri=f"gs://bucket/jobs/j-1/{kind}/{digest}",
            content_type=content_type,
            size_bytes=len(data),
            sha256=digest,
        )

    async def get(self, ref: BlobRef) -> bytes:
        return b""

    async def signed_url(self, ref: BlobRef, *, ttl_seconds: int) -> str:
        return f"{ref.uri}?ttl={ttl_seconds}"


def test_fakes_satisfy_the_repository_protocols() -> None:
    artifacts: ArtifactRepository = InMemoryArtifactRepository()
    jobs: JobRepository = InMemoryJobRepository()
    requests: RequestRepository = InMemoryRequestRepository()
    blobs: BlobStore = InMemoryBlobStore()
    assert artifacts is not None
    assert jobs is not None
    assert requests is not None
    assert blobs is not None


async def test_artifact_repository_round_trips_with_optimistic_locking() -> None:
    repo = InMemoryArtifactRepository()
    artifact = DerivativeArtifact(job_id="j-1", form_id="form-1", source=SOURCE)
    version = await repo.save(artifact, JobCursor(slice_index=0), expected_version=0)
    assert version == 1
    loaded_artifact, loaded_cursor, loaded_version = await repo.load("j-1")
    assert loaded_version == 1
    assert loaded_cursor.slice_index == 0
    assert isinstance(loaded_artifact, DerivativeArtifact)


async def test_blob_store_put_is_content_addressed() -> None:
    store = InMemoryBlobStore()
    ref = await store.put(b"hello world", content_type="image/jpeg", kind="images")
    assert ref.sha256 == __import__("hashlib").sha256(b"hello world").hexdigest()
    url = await store.signed_url(ref, ttl_seconds=60)
    assert "ttl=60" in url


async def test_job_repository_for_request_is_the_completion_barrier() -> None:
    repo = InMemoryJobRepository()
    await repo.put(
        JobRecord(
            job_id="j-1",
            request_id="req-1",
            form_id="form-1",
            status="done",
            cursor=JobCursor(slice_index=3),
        )
    )
    records = await repo.for_request("req-1")
    assert [r.job_id for r in records] == ["j-1"]
