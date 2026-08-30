"""Labels the CV service must emit. Cropping is out of scope."""

DEPICTS = (
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
)

HEADLINER_SHOT_FROM = ("between_front_seats", "beside_seat")

LABEL_GUIDE = """
engine_bay: open bonnet, engine, battery, yellow dipstick/caps.
seat_front: one or both front seats, shot from the door or cabin, not the ceiling.
seat_rear: rear bench.
vehicle_diagonal: exterior three-quarter of the whole car (front or rear).
headliner: interior roof lining / overhead console / grab handles. Not a seat close-up.
windscreen_interior: looking OUT through the glass from the cabin (dash/mirror in frame).
windscreen_exterior: looking IN through the glass from outside the car.
tyre_tread: close-up of a road wheel/tyre, tread pattern visible.
boot: open cargo area, empty or nearly empty, tailgate up.
boot_underfloor_equipment: spare wheel / jack / triangle / extinguisher under the boot floor.
instrument_cluster: gauges behind the steering wheel, warning lights, odometer.

For headliner ONLY, also set shot_from:
- between_front_seats: camera in the gap between the two front seats, looking up.
  Both front headrests typically in frame; overhead console/dome visible; lining
  sweeps toward the rear.
- beside_seat: camera beside a seat or from the rear; only part of the lining;
  one headrest or grab handles; not a between-seats viewpoint.
"""
