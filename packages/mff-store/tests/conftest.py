"""Fixtures shared by every test module.

`artifact_repo`, `job_repo`, `request_repo` and `blob_store` are parametrised over
every adapter this package ships: `memory` (always), plus `firestore` / `gcs` whenever
`FIRESTORE_EMULATOR_HOST` / `STORAGE_EMULATOR_HOST` point at something actually
reachable. A test written against these fixtures runs against every adapter
automatically — see CONTEXT.md: "If a test only passed against the in-memory adapter,
the Firestore adapter is untested and the Protocol bought nothing."

CI has no emulators and no credentials (see the brief): the `firestore`/`gcs` params
are skipped, not failed, when unreachable, so `make check` stays green offline. To run
the full suite for real:

    docker compose -f docker/compose.dev.yaml up -d firestore gcs
    FIRESTORE_EMULATOR_HOST=localhost:8090 STORAGE_EMULATOR_HOST=http://localhost:4443 \\
        uv run pytest packages/mff-store/tests -q
"""

from __future__ import annotations

import os
import socket
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from mff_store.memory import (
    InMemoryArtifactRepository,
    InMemoryBlobStore,
    InMemoryJobRepository,
    InMemoryRequestRepository,
)


def _reachable(host_port: str, timeout: float = 0.5) -> bool:
    host_port = host_port.split("//", 1)[-1]  # strip a scheme, e.g. "http://gcs:4443"
    host, _, port_s = host_port.rpartition(":")
    if not host or not port_s.isdigit():
        return False
    try:
        with socket.create_connection((host, int(port_s)), timeout=timeout):
            return True
    except OSError:
        return False


def _firestore_available() -> bool:
    host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not host:
        return False
    return _reachable(host)


def _gcs_available() -> bool:
    host = os.environ.get("STORAGE_EMULATOR_HOST")
    if not host:
        return False
    return _reachable(host)


_firestore_param = pytest.param(
    "firestore",
    marks=pytest.mark.skipif(
        not _firestore_available(), reason="FIRESTORE_EMULATOR_HOST not set/reachable"
    ),
)
_gcs_param = pytest.param(
    "gcs",
    marks=pytest.mark.skipif(
        not _gcs_available(), reason="STORAGE_EMULATOR_HOST not set/reachable"
    ),
)

FIRESTORE_ADAPTERS = ["memory", _firestore_param]
GCS_ADAPTERS = ["memory", _gcs_param]


@pytest_asyncio.fixture(params=FIRESTORE_ADAPTERS)
async def artifact_repo(request: pytest.FixtureRequest) -> AsyncIterator[object]:
    if request.param == "memory":
        yield InMemoryArtifactRepository()
        return

    from mff_store.firestore_store import FirestoreArtifactRepository, make_firestore_client

    client = make_firestore_client()
    try:
        yield FirestoreArtifactRepository(client, collection_prefix=f"t{uuid.uuid4().hex[:8]}-")
    finally:
        client.close()  # type: ignore[no-untyped-call]


@pytest_asyncio.fixture(params=FIRESTORE_ADAPTERS)
async def job_repo(request: pytest.FixtureRequest) -> AsyncIterator[object]:
    if request.param == "memory":
        yield InMemoryJobRepository()
        return

    from mff_store.firestore_store import FirestoreJobRepository, make_firestore_client

    client = make_firestore_client()
    try:
        yield FirestoreJobRepository(client, collection_prefix=f"t{uuid.uuid4().hex[:8]}-")
    finally:
        client.close()  # type: ignore[no-untyped-call]


@pytest_asyncio.fixture(params=FIRESTORE_ADAPTERS)
async def request_repo(request: pytest.FixtureRequest) -> AsyncIterator[object]:
    if request.param == "memory":
        yield InMemoryRequestRepository()
        return

    from mff_store.firestore_store import FirestoreRequestRepository, make_firestore_client

    client = make_firestore_client()
    try:
        yield FirestoreRequestRepository(client, collection_prefix=f"t{uuid.uuid4().hex[:8]}-")
    finally:
        client.close()  # type: ignore[no-untyped-call]


@pytest_asyncio.fixture(params=GCS_ADAPTERS)
async def blob_store(request: pytest.FixtureRequest) -> AsyncIterator[object]:
    if request.param == "memory":
        yield InMemoryBlobStore()
        return

    from mff_store.gcs import GcsBlobStore, make_gcs_client

    bucket = f"mff-test-{uuid.uuid4().hex[:8]}"
    client = make_gcs_client()
    client.create_bucket(bucket)  # test-only: production assumes the bucket exists
    try:
        yield GcsBlobStore(client, bucket=bucket)
    finally:
        bucket_ref = client.bucket(bucket)
        for blob in client.list_blobs(bucket):
            blob.delete()
        bucket_ref.delete()
