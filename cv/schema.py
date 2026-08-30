"""Pydantic contracts for CV. Look-fors come from expected_requirements."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ManifestRequirement(BaseModel):
    id: str = Field(description="Stable id, e.g. R-01")
    text: str = Field(description="One checkable requirement in English.")
    source_span: str = Field(
        description="Verbatim substring of the client manifest, typos included."
    )
    expected_count: int = Field(default=1, ge=1)
    constraint: str | None = Field(
        default=None,
        description="Extra constraint if stated, e.g. camera between front seats.",
    )


class ParsedManifest(BaseModel):
    expected_total_photos: int | None = None
    requirements: list[ManifestRequirement]


class Finding(BaseModel):
    """Anything visible that a comment might cite. Not a fixed vehicle-field list."""

    what: str = Field(
        description=(
            "Kind of observation, in the photo's own terms: odometer, check-engine lamp, "
            "oil pressure lamp, coolant, registration plate, bumper misalignment, scratch, …"
        )
    )
    value: str = Field(
        description="State or reading: on/off, 59650 km, illuminated, shifted left, plate text, …"
    )
    evidence: str = Field(default="", description="Optional short visual support.")


class ImageLabel(BaseModel):
    requirement_ids: list[str] = Field(
        default_factory=list,
        description="Requirement ids from the checklist this photo actually supports.",
    )
    constraint_ok: bool | None = Field(
        default=None,
        description=(
            "If a tagged requirement has a constraint: true if this photo satisfies it, "
            "false if the subject is right but the constraint is not. null if none applies."
        ),
    )
    constraint_evidence: str | None = Field(
        default=None,
        description="Why constraint_ok is true or false, from what is in the frame.",
    )
    note: str = Field(default="", description="Short caption of the picture.")
    findings: list[Finding] = Field(
        default_factory=list,
        description=(
            "Maximum documentary detail visible: lamps, gauges, fluids, identifiers, "
            "damage, alignment. Do not limit yourself to a preset form. If the photo is "
            "a cluster, report every lit indicator and every readable value."
        ),
    )
