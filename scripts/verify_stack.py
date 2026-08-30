#!/usr/bin/env python3
"""Prove the Firestore/GCS emulators work before anyone debugs mff-store against them.

Sibling to `verify_mailbox.py`, same principle: separate "our code is wrong" from
"the stack is not up". Writes and reads back a small Firestore document (through
`FirestoreRequestRepository`) and uploads/fetches a blob through `GcsBlobStore` —
the same adapters `packages/mff-store` ships, not a hand-rolled smoke path — then
prints PASS/FAIL.

    docker compose -f docker/compose.dev.yaml up -d firestore gcs
    FIRESTORE_EMULATOR_HOST=localhost:8090 STORAGE_EMULATOR_HOST=http://localhost:4443 \\
        uv run python scripts/verify_stack.py

Needs the workspace virtualenv (`uv run`), unlike `verify_mailbox.py`: it exercises
`mff_store`'s real Firestore/GCS clients rather than the standard library alone.
Exits 0 on success.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

CHECK_TIMEOUT = 10.0


def _require_emulator_vars() -> tuple[str, str]:
    firestore_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    gcs_host = os.environ.get("STORAGE_EMULATOR_HOST")
    missing = [
        name
        for name, value in [
            ("FIRESTORE_EMULATOR_HOST", firestore_host),
            ("STORAGE_EMULATOR_HOST", gcs_host),
        ]
        if not value
    ]
    if missing:
        print(f"FAIL  not set: {', '.join(missing)}")
        print("      docker compose -f docker/compose.dev.yaml up -d firestore gcs")
        print("      FIRESTORE_EMULATOR_HOST=localhost:8090 \\")
        print("      STORAGE_EMULATOR_HOST=http://localhost:4443 \\")
        print("          uv run python scripts/verify_stack.py")
        sys.exit(1)
    assert firestore_host is not None
    assert gcs_host is not None
    return firestore_host, gcs_host


async def _check_firestore(marker: str) -> bool:
    from mff_store.firestore_store import FirestoreRequestRepository, make_firestore_client
    from mff_contracts import RequestRecord

    client = make_firestore_client(project=os.environ.get("MFF_GCP_PROJECT", "mff-local"))
    try:
        repo = FirestoreRequestRepository(client, collection_prefix="verify-stack-")
        record = RequestRecord(
            request_id=marker,
            manifest_raw=f"verify_stack.py marker {marker}",
            requirements=[],
            job_ids=[],
            reply_to="verify-stack@example.test",
            original_message_id=f"<{marker}@example.test>",
            status="running",
        )
        await repo.put(record)
        loaded = await repo.get(marker)
        if loaded is None or loaded.manifest_raw != record.manifest_raw:
            print(f"FAIL  Firestore round trip mismatch: {loaded!r}")
            return False

        # RequestRepository.get returns None for an unknown id rather than raising —
        # confirm that, not just the happy path.
        missing = await repo.get("verify-stack-does-not-exist-" + marker)
        if missing is not None:
            print("FAIL  Firestore returned a record for an id that was never written")
            return False

        print(f"  firestore  wrote and read back request_id={marker!r} OK")
        return True
    finally:
        client.close()  # type: ignore[no-untyped-call]


async def _check_gcs(marker: str) -> bool:
    from mff_store.errors import BlobNotFoundError
    from mff_store.gcs import GcsBlobStore, make_gcs_client

    bucket_name = os.environ.get("MFF_GCS_BUCKET", "mff-local")
    client = make_gcs_client(project=os.environ.get("MFF_GCP_PROJECT", "mff-local"))
    bucket = client.bucket(bucket_name)

    # google-cloud-storage is synchronous (requests-based, with its own retry/backoff
    # on connection failure) — calling it directly here would block the event loop and
    # make the asyncio.wait_for() deadline around this whole check pointless, since a
    # blocking call has no await point for the timeout to interrupt.
    def _ensure_bucket() -> None:
        if not bucket.exists(client=client):
            client.create_bucket(bucket_name)

    await asyncio.to_thread(_ensure_bucket)

    store = GcsBlobStore(client, bucket=bucket_name)
    payload = f"verify_stack.py marker {marker}".encode()

    ref = await store.put(payload, content_type="text/plain", kind="verify-stack")
    fetched = await store.get(ref)
    if fetched != payload:
        print("FAIL  GCS round trip returned different bytes than were uploaded")
        return False

    # Same bytes again must dedupe to the same object (content-addressing).
    ref_again = await store.put(payload, content_type="text/plain", kind="verify-stack")
    if ref_again.uri != ref.uri:
        print(f"FAIL  identical bytes produced two different blobs: {ref.uri} != {ref_again.uri}")
        return False

    try:
        await store.get(ref.model_copy(update={"uri": ref.uri + "-does-not-exist"}))
    except BlobNotFoundError:
        pass
    else:
        print("FAIL  GCS returned bytes for an object that was never written")
        return False

    print(f"  gcs        wrote, deduped and read back {len(payload)} bytes OK")
    return True


async def main_async() -> int:
    firestore_host, gcs_host = _require_emulator_vars()
    print(f"firestore  {firestore_host}")
    print(f"gcs        {gcs_host}")

    marker = uuid.uuid4().hex[:12]
    # A wrong or dead host (wrong port, container not up yet) does not fail fast on
    # its own — the client libraries retry for a long time before giving up. A
    # verifier that can itself hang indefinitely defeats the purpose, so every check
    # gets an explicit deadline.
    try:
        firestore_ok = await asyncio.wait_for(_check_firestore(marker), timeout=CHECK_TIMEOUT)
    except TimeoutError:
        print(f"FAIL  Firestore: no response within {CHECK_TIMEOUT:.0f}s")
        print("      is the firestore emulator up? docker compose ... up -d firestore")
        firestore_ok = False
    except Exception as exc:  # noqa: BLE001 — this script's whole job is to report, not raise
        print(f"FAIL  Firestore: {type(exc).__name__}: {exc}")
        print("      is the firestore emulator up? docker compose ... up -d firestore")
        firestore_ok = False

    try:
        gcs_ok = await asyncio.wait_for(_check_gcs(marker), timeout=CHECK_TIMEOUT)
    except TimeoutError:
        print(f"FAIL  GCS: no response within {CHECK_TIMEOUT:.0f}s")
        print("      is the gcs emulator up? docker compose ... up -d gcs")
        gcs_ok = False
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL  GCS: {type(exc).__name__}: {exc}")
        print("      is the gcs emulator up? docker compose ... up -d gcs")
        gcs_ok = False

    if firestore_ok and gcs_ok:
        print("PASS  Firestore and GCS both work: write, read, dedupe, not-found all correct")
        code = 0
    else:
        code = 1

    # Not a normal return: a timed-out GCS check (CHECK_TIMEOUT above) leaves an
    # abandoned worker thread still retrying inside google-api-core's own backoff —
    # asyncio.wait_for's cancellation cannot reach it, because it is synchronous,
    # blocking code with no await point for cancellation to land on. That thread is
    # not a daemon, so `asyncio.run()`'s own cleanup (`shutdown_default_executor`)
    # would block *this* coroutine's return waiting to join it — for however long
    # that backoff takes, up to several minutes — despite already having printed the
    # diagnosis above. os._exit terminates immediately, skipping that join along
    # with the rest of the interpreter's normal shutdown machinery, which is exactly
    # what a script whose job ends at the FAIL/PASS line above wants.
    sys.stdout.flush()
    os._exit(code)


if __name__ == "__main__":
    asyncio.run(main_async())
