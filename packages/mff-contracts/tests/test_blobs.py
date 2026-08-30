"""BlobRef, ImageAnalysis, RequirementSpec, JobImage — reqs 13. No BoundingBox, no crop."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mff_contracts import BlobRef, ImageAnalysis, JobImage, RequirementHit, RequirementSpec


def test_blob_ref_round_trips_through_json() -> None:
    blob = BlobRef(
        uri="gs://bucket/jobs/j-1/images/deadbeef",
        content_type="image/jpeg",
        size_bytes=204800,
        sha256="deadbeef",
    )
    restored = BlobRef.model_validate_json(blob.model_dump_json())
    assert restored == blob


def test_image_analysis_constraint_is_per_hit() -> None:
    good = ImageAnalysis(
        file="a.jpg",
        hits=[RequirementHit(id="R-04", constraint_ok=True)],
    )
    bad = ImageAnalysis(
        file="b.jpg",
        hits=[RequirementHit(id="R-04", constraint_ok=False)],
    )
    assert [h.id for h in good.hits] == [h.id for h in bad.hits] == ["R-04"]
    assert good.hits[0].constraint_ok is True
    assert bad.hits[0].constraint_ok is False


def test_image_analysis_empty_hits_is_unknown() -> None:
    assert ImageAnalysis(file="a.jpg").is_known is False
    assert ImageAnalysis(file="a.jpg", hits=[RequirementHit(id="R-01")]).is_known is True


def test_requirement_spec_is_a_projection_not_a_copy() -> None:
    """The vision service gets what it can act on — not manifest offsets or slice scopes."""
    fields = set(RequirementSpec.model_fields)
    assert fields == {"id", "text", "constraint"}


def test_job_image_source_is_attachment_or_embedded() -> None:
    blob = BlobRef(uri="gs://b/x", content_type="image/jpeg", size_bytes=1, sha256="x")
    attachment = JobImage(blob=blob, original_filename="a.jpg", source="attachment")
    embedded = JobImage(blob=blob, original_filename="a.jpg", source="embedded")
    assert attachment.analysis is None
    assert embedded.source == "embedded"


def test_job_image_rejects_an_unknown_source() -> None:
    blob = BlobRef(uri="gs://b/x", content_type="image/jpeg", size_bytes=1, sha256="x")
    with pytest.raises(ValidationError):
        JobImage(blob=blob, original_filename="a.jpg", source="scanned")
