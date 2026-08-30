"""Everything about the Firestore/GCS adapters that does *not* need a reachable
emulator: client construction, reference building (collections, documents, buckets,
blobs — all local, no RPC), and the pure helper functions.

The methods that actually issue RPCs (`save`, `load`, `put`, `get`, `for_request`,
`signed_url`) are exercised by `test_artifact_repository.py` / `test_job_repository.py`
/ `test_request_repository.py` / `test_blob_store.py` through the `firestore`/`gcs`
adapter params in `conftest.py` — which run for real against the emulators when
`FIRESTORE_EMULATOR_HOST` / `STORAGE_EMULATOR_HOST` are set and reachable, and skip
(never fail) otherwise. That split is what keeps CI offline (no emulators, no
credentials) while still proving the adapters work end-to-end wherever emulators are
available. See the package README for how to run that.
"""

from __future__ import annotations

import os

import google.cloud.storage as storage  # no py.typed, but `import a.b as c` needs no ignore
import pytest
from factories import make_artifact, make_netnew_artifact
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import firestore

from mff_store.firestore_store import (
    FirestoreArtifactRepository,
    FirestoreJobRepository,
    FirestoreRequestRepository,
    _artifact_from_doc,
    _artifact_kind,
    make_firestore_client,
)
from mff_store.gcs import GcsBlobStore, _emulator_endpoint, _object_name_from_uri, make_gcs_client


@pytest.fixture
def clean_emulator_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)


def test_make_firestore_client_against_emulator_var_needs_no_network(
    clean_emulator_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the Mock-credentials trick: this must not touch the network
    or the filesystem for ADC — it must succeed purely from the env var being set."""
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:1")
    client = make_firestore_client()
    assert isinstance(client, firestore.AsyncClient)


def test_make_firestore_client_without_emulator_var_uses_real_adc(
    clean_emulator_env: None,
) -> None:
    """No emulator var -> falls through to normal Application Default Credentials
    discovery, exactly like real Firestore usage. This sandbox has no ADC configured,
    so the deterministic, offline-safe assertion is that it raises rather than
    silently talking to something unexpected."""
    with pytest.raises(DefaultCredentialsError):
        make_firestore_client(project="test")


def test_make_gcs_client_against_emulator_var_needs_no_network(
    clean_emulator_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "localhost:1")
    client = make_gcs_client()
    assert isinstance(client, storage.Client)


def test_make_gcs_client_without_emulator_var_uses_real_adc(clean_emulator_env: None) -> None:
    with pytest.raises(DefaultCredentialsError):
        make_gcs_client(project="test")


def test_emulator_endpoint_adds_scheme_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "gcs:4443")
    assert _emulator_endpoint() == "http://gcs:4443"


def test_emulator_endpoint_keeps_explicit_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "https://gcs:4443")
    assert _emulator_endpoint() == "https://gcs:4443"


def test_emulator_endpoint_none_when_unset(
    clean_emulator_env: None,
) -> None:
    assert _emulator_endpoint() is None


def test_artifact_kind_and_round_trip_through_doc_shape() -> None:
    artifact = make_artifact("job-x")
    kind = _artifact_kind(artifact)
    assert kind == "derivative"

    rebuilt = _artifact_from_doc(kind, artifact.model_dump(mode="json"))
    assert rebuilt == artifact


def test_artifact_kind_and_round_trip_through_doc_shape_net_new() -> None:
    artifact = make_netnew_artifact("WN-7020U")
    kind = _artifact_kind(artifact)
    assert kind == "net_new"

    rebuilt = _artifact_from_doc(kind, artifact.model_dump(mode="json"))
    assert rebuilt == artifact


def test_artifact_from_doc_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown artifact kind"):
        _artifact_from_doc("not-a-real-kind", {})


def test_object_name_from_uri_round_trips() -> None:
    assert _object_name_from_uri("gs://mff-local/image/deadbeef", "mff-local") == "image/deadbeef"


def test_object_name_from_uri_rejects_foreign_bucket() -> None:
    with pytest.raises(ValueError, match="does not belong to bucket"):
        _object_name_from_uri("gs://other-bucket/image/deadbeef", "mff-local")


def test_firestore_repositories_construct_without_a_reachable_server(
    clean_emulator_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Building collection/document references is local bookkeeping in the client
    library, not an RPC — constructing the adapters must not require connectivity."""
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:1")
    client = make_firestore_client()

    artifact_repo = FirestoreArtifactRepository(client, collection_prefix="wiring-test-")
    assert artifact_repo.fail_before_cursor_write is False
    FirestoreJobRepository(client, collection_prefix="wiring-test-")
    FirestoreRequestRepository(client, collection_prefix="wiring-test-")


def test_gcs_blob_store_constructs_without_a_reachable_server(
    clean_emulator_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "localhost:1")
    client = make_gcs_client()
    store = GcsBlobStore(client, bucket="mff-local")
    assert store._bucket_name == "mff-local"


async def test_gcs_signed_url_emulator_branch_needs_no_network(
    clean_emulator_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the *real* V4-signing branch needs a live service account; the emulator
    branch is plain string formatting and must work with nothing reachable."""
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "localhost:1")
    client = make_gcs_client()
    store = GcsBlobStore(client, bucket="mff-local")

    ref = make_artifact("job-x").source.model_copy(update={"uri": "gs://mff-local/image/abc"})
    url = await store.signed_url(ref, ttl_seconds=60)
    assert url == "http://localhost:1/storage/v1/b/mff-local/o/image%2Fabc?alt=media"


def test_env_vars_are_the_only_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """No "am I local" branch anywhere: flipping the env var is the only thing that
    changes which endpoint a fresh client points at."""
    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    assert _emulator_endpoint() is None
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "gcs:4443")
    assert _emulator_endpoint() == "http://gcs:4443"
    assert os.environ["STORAGE_EMULATOR_HOST"] == "gcs:4443"
