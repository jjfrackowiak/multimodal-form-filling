"""BlobRef, ImageAnalysis, RequirementSpec, JobImage — reqs 13. No BoundingBox, no crop."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mff_contracts import BlobRef, ImageAnalysis, JobImage, RequirementSpec


def test_blob_ref_round_trips_through_json() -> None:
    blob = BlobRef(
        uri="gs://bucket/jobs/j-1/images/deadbeef",
        content_type="image/jpeg",
        size_bytes=204800,
        sha256="deadbeef",
    )
    restored = BlobRef.model_validate_json(blob.model_dump_json())
    assert restored == blob


def test_image_analysis_depicts_and_shot_from_are_separate_questions() -> None:
    good = ImageAnalysis(file="a.jpg", depicts="headliner", shot_from="between_front_seats")
    bad = ImageAnalysis(file="b.jpg", depicts="headliner", shot_from="beside_seat")
    assert good.depicts == bad.depicts
    assert good.shot_from != bad.shot_from


def test_image_analysis_confidence_defaults_to_one() -> None:
    assert ImageAnalysis(file="a.jpg", depicts="boot").confidence == 1.0


def test_image_analysis_rejects_impossible_confidence() -> None:
    with pytest.raises(ValidationError):
        ImageAnalysis(file="a.jpg", depicts="boot", confidence=1.5)


def test_image_analysis_is_known_is_false_only_for_unknown() -> None:
    assert ImageAnalysis(file="a.jpg", depicts="unknown", confidence=0.0).is_known is False
    assert ImageAnalysis(file="a.jpg", depicts="boot").is_known is True


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
