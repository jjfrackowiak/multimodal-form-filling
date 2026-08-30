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


class ImageRef(BaseModel):
    """How an image is named across the wire. Production URIs are gs://."""

    uri: str


class InventoryRequest(BaseModel):
    """Editor → CV tool. Same payload as mff-vision / vision-stub."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "images": [{"uri": "gs://bucket/jobs/abc/front.jpg"}],
                "requirements": [
                    {
                        "id": "R-01",
                        "text": "A photograph of the front of the vehicle.",
                        "constraint": None,
                    }
                ],
            }
        }
    )

    images: list[ImageRef] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    image_prefix: str | None = Field(
        default=None, description="gs://bucket/prefix/ — extra objects under it"
    )
    manifest: str | None = None


class InventoryResponse(BaseModel):
    images: list[InventoryImage]
    exact_duplicate_pairs: list[list[str]] = Field(default_factory=list)
    duration_seconds: float
    model: str
    project: str
