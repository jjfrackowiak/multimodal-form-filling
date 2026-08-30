"""`schema_version` is present on both artifacts.

These persist (Firestore documents outlive deploys), so a shape change must fail loudly
rather than parse partially. Enforced here as "a positive integer" — a zero or negative
version is treated the same as a missing one.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mff_contracts import BlobRef, DerivativeArtifact, FormDraft, NetNewArtifact

SOURCE = BlobRef(
    uri="gs://bucket/jobs/j-1/source/abc",
    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes=1024,
    sha256="abc123",
)


def test_derivative_artifact_defaults_schema_version_to_one() -> None:
    artifact = DerivativeArtifact(job_id="j-1", form_id="form-1", source=SOURCE)
    assert artifact.schema_version == 1


def test_derivative_artifact_rejects_a_zero_schema_version() -> None:
    with pytest.raises(ValidationError):
        DerivativeArtifact(job_id="j-1", form_id="form-1", source=SOURCE, schema_version=0)


def test_net_new_artifact_defaults_schema_version_to_one() -> None:
    artifact = NetNewArtifact(job_id="j-1", form_id="form-1", draft=FormDraft())
    assert artifact.schema_version == 1


def test_net_new_artifact_rejects_a_negative_schema_version() -> None:
    with pytest.raises(ValidationError):
        NetNewArtifact(job_id="j-1", form_id="form-1", draft=FormDraft(), schema_version=-1)


def test_net_new_artifact_accepts_an_explicit_later_version() -> None:
    artifact = NetNewArtifact(job_id="j-1", form_id="form-1", draft=FormDraft(), schema_version=2)
    assert artifact.schema_version == 2


def test_derivative_artifact_requires_a_job_id() -> None:
    """`form_id` alone is the client's filename or folder name and collides across
    requests; `save` keys on `artifact.job_id`, so it must be present."""
    with pytest.raises(ValidationError):
        DerivativeArtifact(form_id="form-1", source=SOURCE)  # type: ignore[call-arg]


def test_net_new_artifact_requires_a_job_id() -> None:
    with pytest.raises(ValidationError):
        NetNewArtifact(form_id="form-1", draft=FormDraft())  # type: ignore[call-arg]
