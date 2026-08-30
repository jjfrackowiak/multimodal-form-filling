"""Artifact = DerivativeArtifact | NetNewArtifact — one artifact type per mode (req 9)."""

from __future__ import annotations

from pydantic import TypeAdapter

from mff_contracts import Artifact, BlobRef, DerivativeArtifact, FormDraft, NetNewArtifact

SOURCE = BlobRef(
    uri="gs://bucket/jobs/j-1/source/abc",
    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes=1024,
    sha256="abc123",
)

_ADAPTER: TypeAdapter[Artifact] = TypeAdapter(Artifact)


def test_derivative_artifact_round_trips_through_the_union() -> None:
    artifact: Artifact = DerivativeArtifact(form_id="form-1", source=SOURCE)
    restored = _ADAPTER.validate_json(_ADAPTER.dump_json(artifact))
    assert isinstance(restored, DerivativeArtifact)
    assert restored.form_id == "form-1"


def test_net_new_artifact_round_trips_through_the_union() -> None:
    artifact: Artifact = NetNewArtifact(form_id="form-1", draft=FormDraft())
    restored = _ADAPTER.validate_json(_ADAPTER.dump_json(artifact))
    assert isinstance(restored, NetNewArtifact)
    assert restored.draft.schema_version == 1
