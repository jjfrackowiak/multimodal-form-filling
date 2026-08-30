"""GCS adapter — weight, not shape.

Every `.docx` and every image goes here rather than into a Firestore document (capped
at 1 MiB). `BlobStore.put` (frozen) carries no `job_id`, so addressing is global —
content-addressed by `sha256(data)` under `gs://<bucket>/<kind>/<sha256>` — rather than
scoped per job; identical bytes dedupe across the whole store, a superset of "dedupe
within one job".

Switched by the `STORAGE_EMULATOR_HOST` environment variable only — no "am I local"
branch anywhere in this module. `google-cloud-storage` has moved where it reads that
variable from across versions; this module reads it itself and passes `api_endpoint`
explicitly (verified against the pinned 3.13.1) rather than relying on whichever
resolution order the installed version happens to implement.

`google-cloud-storage` has no async client — it is a synchronous, `requests`-based
library. Every network call here runs under `asyncio.to_thread` so it does not block
the event loop the rest of the service runs on.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import timedelta
from typing import TYPE_CHECKING
from urllib.parse import quote

import google.cloud.storage as storage  # no py.typed — see the mypy override in pyproject.toml
from google.api_core.exceptions import NotFound
from google.auth.credentials import AnonymousCredentials

from mff_contracts import BlobRef, BlobStore

from .errors import BlobNotFoundError

__all__ = ["GcsBlobStore", "make_gcs_client"]


def _emulator_endpoint() -> str | None:
    host = os.environ.get("STORAGE_EMULATOR_HOST")
    if not host:
        return None
    return host if "://" in host else f"http://{host}"


def make_gcs_client(project: str | None = None) -> storage.Client:
    """Build a `Client` that works against both the emulator and real GCS.

    Passed explicitly rather than left to the library's own env-var handling: newer
    `google-cloud-storage` may prefer `client_options={"api_endpoint": ...}` over
    `STORAGE_EMULATOR_HOST` resolution — verify against the pinned version before
    trusting either form (see this package's `pyproject.toml`).
    """
    endpoint = _emulator_endpoint()
    if endpoint:
        return storage.Client(
            project=project or "mff-local",
            credentials=AnonymousCredentials(),  # type: ignore[no-untyped-call]
            client_options={"api_endpoint": endpoint},
        )
    return storage.Client(project=project)


def _object_name_from_uri(uri: str, bucket: str) -> str:
    prefix = f"gs://{bucket}/"
    if not uri.startswith(prefix):
        raise ValueError(f"BlobRef {uri!r} does not belong to bucket {bucket!r}")
    return uri[len(prefix) :]


class GcsBlobStore:
    """Assumes `bucket` already exists — provisioning it is the deployment owner's
    job (Terraform or otherwise), not this adapter's. Tests create it directly against
    the emulator; see `tests/conftest.py`."""

    def __init__(self, client: storage.Client, *, bucket: str) -> None:
        self._client = client
        self._bucket_name = bucket
        self._bucket = client.bucket(bucket)

    # pragma: no cover justification for put()/get() below, and the real-signing
    # branch of signed_url(): CI is offline (no emulators, no credentials — see
    # CONTEXT.md / the brief), so these bodies cannot be exercised there. They are
    # exercised for real by the shared, adapter-parametrised suite
    # (tests/test_blob_store.py) via the "gcs" param in tests/conftest.py, wherever
    # STORAGE_EMULATOR_HOST is actually reachable — that run is what proves this
    # code, not this metric.
    async def put(  # pragma: no cover
        self, data: bytes, *, content_type: str, kind: str
    ) -> BlobRef:
        sha256 = hashlib.sha256(data).hexdigest()
        object_name = f"{kind}/{sha256}"
        blob = self._bucket.blob(object_name)

        def _upload() -> None:
            # Content-addressed: identical bytes already live at this path, so a
            # retried job re-points at the existing object rather than writing a
            # second copy.
            if not blob.exists(client=self._client):
                blob.upload_from_string(data, content_type=content_type, client=self._client)

        await asyncio.to_thread(_upload)
        return BlobRef(
            uri=f"gs://{self._bucket_name}/{object_name}",
            content_type=content_type,
            size_bytes=len(data),
            sha256=sha256,
        )

    async def get(self, ref: BlobRef) -> bytes:  # pragma: no cover — see put() above
        object_name = _object_name_from_uri(ref.uri, self._bucket_name)
        blob = self._bucket.blob(object_name)

        def _download() -> bytes:
            try:
                data: bytes = blob.download_as_bytes(client=self._client)
            except NotFound as exc:
                raise BlobNotFoundError(f"no blob at {ref.uri!r}") from exc
            return data

        return await asyncio.to_thread(_download)

    async def signed_url(self, ref: BlobRef, *, ttl_seconds: int) -> str:
        object_name = _object_name_from_uri(ref.uri, self._bucket_name)

        endpoint = _emulator_endpoint()
        if endpoint:
            # Real V4 signing needs a service-account private key, which
            # AnonymousCredentials does not carry and the emulator does not check —
            # a direct media-download URL against the emulator's JSON API stands in.
            encoded = quote(object_name, safe="")
            return f"{endpoint}/storage/v1/b/{self._bucket_name}/o/{encoded}?alt=media"

        return await self._generate_v4_signed_url(object_name, ttl_seconds)

    # Real signing needs a service account with an actual private key, which nothing
    # in CI (or this local dev setup) has — only exercised against real GCS.
    async def _generate_v4_signed_url(  # pragma: no cover
        self, object_name: str, ttl_seconds: int
    ) -> str:
        blob = self._bucket.blob(object_name)

        def _sign() -> str:
            url: str = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=ttl_seconds),
                client=self._client,
            )
            return url

        return await asyncio.to_thread(_sign)


if TYPE_CHECKING:  # pragma: no cover
    # Structural-conformance check against the frozen Protocol — see memory.py.
    def _conforms(client: storage.Client) -> None:
        _blob_store: BlobStore = GcsBlobStore(client, bucket="test")
