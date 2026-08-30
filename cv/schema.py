"""Pydantic contracts for CV.

The look-fors come from the *manifest*, not a frozen car ontology.
Vertex fills these via response_schema.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DisplayWarning(BaseModel):
    text: str = Field(description="Verbatim text on the cluster, original language.")
    meaning: str = Field(default="", description="Short English gloss.")


class ManifestRequirement(BaseModel):
    id: str = Field(description="Stable id, e.g. R-01")
    text: str = Field(description="One checkable requirement in English.")
    source_span: str = Field(
        description="Verbatim substring of the client manifest, typos included."
    )
    expected_count: int = Field(default=1, ge=1)
    constraint: str | None = Field(
        default=None,
        description="Extra constraint if the manifest states one, e.g. camera between front seats.",
    )


class ParsedManifest(BaseModel):
    expected_total_photos: int | None = None
    requirements: list[ManifestRequirement]


class ImageLabel(BaseModel):
    """One photo, scored against the requirements passed in the request."""

    requirement_ids: list[str] = Field(
        default_factory=list,
        description="Zero or more requirement ids from the manifest that this photo actually depicts.",
    )
    constraint_ok: bool | None = Field(
        default=None,
        description=(
            "If a tagged requirement has a constraint (e.g. headliner from between the seats): "
            "true if this photo satisfies it, false if it is the right subject but wrong pose. "
            "null if no constraint applies."
        ),
    )
    note: str = Field(default="", description="Short English caption.")
    odometer_km: int | None = Field(
        default=None,
        description="Integer km from the cluster if readable (e.g. 59650).",
    )
    warnings: list[DisplayWarning] = Field(
        default_factory=list,
        description="Cluster warning messages, original language + English meaning.",
    )
    registration: str | None = Field(
        default=None,
        description="Number plate if clearly readable.",
    )
    seat_side: Literal["driver", "passenger", "both"] | None = None
    pose_evidence: str | None = Field(
        default=None,
        description="Visual proof for constraint_ok when a pose constraint exists.",
    )

    @field_validator("odometer_km", mode="before")
    @classmethod
    def parse_km(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, int):
            return v
        s = str(v).lower().replace("km", "").replace(" ", "").replace(",", "")
        try:
            return int(s)
        except ValueError:
            return None
