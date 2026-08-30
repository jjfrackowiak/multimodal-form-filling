"""Firestore adapter — shape, not weight.

Firestore stores the artifact JSON and `JobRecord`/`RequestRecord`; GCS
(`mff_store.gcs`) stores every `.docx` and image, because Firestore caps a document at
1 MiB and the fixture's reviewed `.docx` alone is 2.8 MB. Getting this backwards
surfaces as a hard write failure on exactly the large documents the product exists to
handle.

Switched by the `FIRESTORE_EMULATOR_HOST` environment variable only — no "am I local"
branch anywhere in this module.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import google.auth.credentials
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from mff_contracts import (
    Artifact,
    ArtifactRepository,
    DerivativeArtifact,
    JobCursor,
    JobRecord,
    JobRepository,
    NetNewArtifact,
    RequestRecord,
    RequestRepository,
)

from .errors import NotFoundError, VersionConflict

__all__ = [
    "FirestoreArtifactRepository",
    "FirestoreJobRepository",
    "FirestoreRequestRepository",
    "make_firestore_client",
]


def make_firestore_client(project: str | None = None) -> firestore.AsyncClient:
    """Build an `AsyncClient` that works against both the emulator and real Firestore.

    `AsyncClient` does **not** fall back to anonymous access against the emulator the
    way the sync `Client` does — since google-cloud-firestore 2.0, it still runs normal
    ADC discovery and raises `DefaultCredentialsError` unless something that satisfies
    the `Credentials` interface is passed explicitly (googleapis/python-firestore#250).
    A `Mock(spec=...)` satisfies isinstance/attribute checks without needing a real
    token, which is all the emulator (which does not check credentials) requires.
    """
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return firestore.AsyncClient(
            project=project or "mff-local",
            credentials=Mock(spec=google.auth.credentials.Credentials),
        )
    return firestore.AsyncClient(project=project)


def _artifact_kind(artifact: Artifact) -> str:
    if isinstance(artifact, DerivativeArtifact):
        return "derivative"
    if isinstance(artifact, NetNewArtifact):
        return "net_new"
    raise TypeError(f"unknown artifact type: {type(artifact)!r}")  # pragma: no cover


def _artifact_from_doc(kind: str, data: dict[str, Any]) -> Artifact:
    if kind == "derivative":
        return DerivativeArtifact.model_validate(data)
    if kind == "net_new":
        return NetNewArtifact.model_validate(data)
    raise ValueError(f"unknown artifact kind in Firestore document: {kind!r}")  # pragma: no cover


class FirestoreArtifactRepository:
    """Keyed by `artifact.form_id` — see `InMemoryArtifactRepository` for why: the
    frozen `ArtifactRepository.save` signature carries no `job_id`.

    The artifact and the cursor are two documents (`{prefix}artifacts/{key}` and
    `{prefix}cursors/{key}`), written together inside one Firestore transaction — the
    atomicity requirement this branch exists for. Any exception raised inside the
    transactional callable (a version conflict, a simulated crash, a real one) rolls
    the whole transaction back; Firestore never partially commits one, and the
    transaction wrapper does not retry on an application exception — only on Firestore
    contention (`Aborted`), which sequential slice writes never produce.
    """

    def __init__(self, client: firestore.AsyncClient, *, collection_prefix: str = "") -> None:
        self._client = client
        self._artifacts = client.collection(f"{collection_prefix}artifacts")
        self._cursors = client.collection(f"{collection_prefix}cursors")
        # Test seam only — see InMemoryArtifactRepository.fail_before_cursor_write.
        self.fail_before_cursor_write = False

    # pragma: no cover justification for every RPC-issuing method below: CI is
    # offline (no emulators, no credentials — see CONTEXT.md / the brief), so these
    # bodies cannot be exercised there. They are exercised for real by the shared,
    # adapter-parametrised suite (tests/test_artifact_repository.py and friends) via
    # the "firestore" param in tests/conftest.py, wherever FIRESTORE_EMULATOR_HOST is
    # actually reachable — that run is what proves this code, not this metric.
    async def save(  # pragma: no cover
        self, artifact: Artifact, cursor: JobCursor, *, expected_version: int
    ) -> int:
        key = artifact.form_id
        artifact_ref = self._artifacts.document(key)
        cursor_ref = self._cursors.document(key)
        kind = _artifact_kind(artifact)
        fail_before_cursor_write = self.fail_before_cursor_write

        @firestore.async_transactional
        async def _txn(transaction: firestore.AsyncTransaction) -> int:
            snapshot = await artifact_ref.get(transaction=transaction)
            doc = snapshot.to_dict() if snapshot.exists else None
            actual_version = doc["version"] if doc is not None else 0
            if actual_version != expected_version:
                raise VersionConflict(key, expected_version, actual_version)

            new_version = expected_version + 1
            transaction.set(
                artifact_ref,
                {
                    "kind": kind,
                    "data": artifact.model_dump(mode="json"),
                    "version": new_version,
                },
            )
            if fail_before_cursor_write:
                raise RuntimeError("simulated crash between artifact and cursor write")
            transaction.set(
                cursor_ref,
                {"data": cursor.model_dump(mode="json"), "version": new_version},
            )
            return new_version

        transaction = self._client.transaction()
        return await _txn(transaction)

    async def load(self, job_id: str) -> tuple[Artifact, JobCursor, int]:  # pragma: no cover
        artifact_snap = await self._artifacts.document(job_id).get()
        cursor_snap = await self._cursors.document(job_id).get()
        if not artifact_snap.exists or not cursor_snap.exists:
            raise NotFoundError(f"no artifact for job_id={job_id!r}")
        artifact_doc = artifact_snap.to_dict() or {}
        cursor_doc = cursor_snap.to_dict() or {}
        artifact = _artifact_from_doc(artifact_doc["kind"], artifact_doc["data"])
        cursor = JobCursor.model_validate(cursor_doc["data"])
        version: int = artifact_doc["version"]
        return artifact, cursor, version


class FirestoreJobRepository:
    def __init__(self, client: firestore.AsyncClient, *, collection_prefix: str = "") -> None:
        self._jobs = client.collection(f"{collection_prefix}jobs")

    async def put(self, record: JobRecord) -> None:  # pragma: no cover — see save() above
        await self._jobs.document(record.job_id).set(record.model_dump(mode="json"))

    async def get(self, job_id: str) -> JobRecord | None:  # pragma: no cover — see save() above
        snap = await self._jobs.document(job_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict()
        return JobRecord.model_validate(data) if data is not None else None

    async def for_request(self, request_id: str) -> list[JobRecord]:  # pragma: no cover
        query = self._jobs.where(filter=FieldFilter("request_id", "==", request_id))  # the barrier
        return [JobRecord.model_validate(snap.to_dict()) async for snap in query.stream()]


class FirestoreRequestRepository:
    def __init__(self, client: firestore.AsyncClient, *, collection_prefix: str = "") -> None:
        self._requests = client.collection(f"{collection_prefix}requests")

    async def put(self, record: RequestRecord) -> None:  # pragma: no cover — see save() above
        await self._requests.document(record.request_id).set(record.model_dump(mode="json"))

    async def get(self, request_id: str) -> RequestRecord | None:  # pragma: no cover
        snap = await self._requests.document(request_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict()
        return RequestRecord.model_validate(data) if data is not None else None


if TYPE_CHECKING:  # pragma: no cover
    # Structural-conformance check against the frozen Protocols — see memory.py.
    def _conforms(client: firestore.AsyncClient) -> None:
        _artifact_repo: ArtifactRepository = FirestoreArtifactRepository(client)
        _job_repo: JobRepository = FirestoreJobRepository(client)
        _request_repo: RequestRepository = FirestoreRequestRepository(client)
