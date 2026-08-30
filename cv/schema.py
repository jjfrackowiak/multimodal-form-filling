"""Contracts. Checklist comes from expected_requirements.yaml, not a car enum."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Requirement(BaseModel):
    id: str
    text: str
    source_span: str = ""
    expected_count: int = Field(default=1, ge=1)
    constraint: str | None = None


class ParsedChecklist(BaseModel):
    expected_total_photos: int | None = None
    requirements: list[Requirement]


class Finding(BaseModel):
    what: str = Field(description="What was seen: lamp, reading, plate, damage, leak, …")
    value: str = Field(description="State or reading: on, 59650 km, WI 022LC, shifted, …")
    evidence: str = Field(default="", description="Short visual support if useful.")


class RequirementHit(BaseModel):
    id: str = Field(description="Checklist id this photo supports.")
    constraint_ok: bool | None = Field(
        default=None,
        description="If this id has a constraint: true/false from the frame; else null.",
    )
    constraint_evidence: str | None = None


class ImageLabel(BaseModel):
    hits: list[RequirementHit] = Field(
        default_factory=list,
        description="Checklist items this photo actually supports. One entry per id.",
    )
    note: str = Field(default="", description="Short caption.")
    findings: list[Finding] = Field(
        default_factory=list,
        description=(
            "Everything documentary in the frame: warning lamps on/off, gauges, "
            "identifiers, damage. Not a fixed form."
        ),
    )


class InventoryImage(BaseModel):
    file: str
    uri: str | None = Field(
        default=None,
        description="Original gs:// URI when the tool was called over HTTP.",
    )
    hits: list[RequirementHit] = Field(default_factory=list)
    note: str = ""
    findings: list[Finding] = Field(default_factory=list)
    exact_duplicate_of: str | None = None

    @property
    def requirement_ids(self) -> list[str]:
        return [h.id for h in self.hits]


class Inventory(BaseModel):
    checklist: ParsedChecklist
    images: list[InventoryImage]
    exact_duplicate_pairs: list[list[str]] = Field(default_factory=list)


class InventoryRequest(BaseModel):
    """Editor → CV tool. Photos stay in GCS; this payload is JSON only."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "checklist": {
                    "requirements": [
                        {
                            "id": "R-01",
                            "text": "Front of the vehicle",
                            "source_span": "front of the vehicle",
                            "expected_count": 1,
                        }
                    ]
                },
                "image_uris": ["gs://bucket/jobs/abc/front.jpg"],
            }
        }
    )

    checklist: ParsedChecklist
    image_uris: list[str] = Field(default_factory=list, description="gs:// URIs")
    image_prefix: str | None = Field(
        default=None, description="gs://bucket/prefix/ — image objects under it"
    )
    manifest: str | None = None


class InventoryResponse(BaseModel):
    inventory: Inventory
    duration_seconds: float
    model: str
    project: str
