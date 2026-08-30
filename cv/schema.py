"""Structured inventory label. Vertex fills this via response_schema — no 'JSON only' prompt."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Depicts = Literal[
    "engine_bay",
    "seat_front",
    "seat_rear",
    "vehicle_diagonal",
    "headliner",
    "windscreen_interior",
    "windscreen_exterior",
    "tyre_tread",
    "boot",
    "boot_underfloor_equipment",
    "instrument_cluster",
]

ShotFrom = Literal["between_front_seats", "beside_seat"]
SeatSide = Literal["driver", "passenger", "both"]
Diagonal = Literal["front_left", "front_right", "rear_left", "rear_right"]


class DisplayWarning(BaseModel):
    text: str = Field(description="Verbatim text on the cluster, original language.")
    meaning: str = Field(default="", description="Short English gloss.")


class ImageLabel(BaseModel):
    depicts: Depicts = Field(
        description=(
            "Primary subject. engine_bay=open bonnet; seat_front/seat_rear=cabin seats; "
            "vehicle_diagonal=exterior 3/4 of the car; headliner=roof lining/overhead console; "
            "windscreen_interior=looking out from the cabin; windscreen_exterior=looking in "
            "from outside; tyre_tread=wheel close-up; boot=open cargo; "
            "boot_underfloor_equipment=spare/jack/triangle; instrument_cluster=gauges."
        )
    )
    shot_from: ShotFrom | None = Field(
        default=None,
        description=(
            "Only when depicts is headliner. between_front_seats: camera in the gap between "
            "the two front seats, both headrests often in frame, overhead console visible. "
            "beside_seat: from the side/rear; only part of the lining."
        ),
    )
    note: str = Field(default="", description="Short English caption of what is visible.")
    odometer_km: int | None = Field(
        default=None,
        description="Integer km from the cluster if readable, no spaces (e.g. 59650).",
    )
    warnings: list[DisplayWarning] = Field(
        default_factory=list,
        description="Cluster warning messages. Quote original language; gearbox/oil/brake matter.",
    )
    registration: str | None = Field(
        default=None,
        description="Number plate if clearly readable.",
    )
    seat_side: SeatSide | None = Field(
        default=None,
        description="For seat_front: driver, passenger, or both.",
    )
    diagonal: Diagonal | None = Field(
        default=None,
        description="For vehicle_diagonal: which three-quarter.",
    )
    pose_evidence: str | None = Field(
        default=None,
        description="For headliner: visual proof of shot_from (headrests, console, how much lining).",
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

    @model_validator(mode="after")
    def pose_only_for_headliner(self):
        if self.depicts == "headliner":
            if self.shot_from is None:
                raise ValueError("headliner requires shot_from")
        else:
            self.shot_from = None
        return self
