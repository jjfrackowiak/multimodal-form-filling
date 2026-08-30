# mff-vision

The seam between the AI editor and image understanding (req 13).

**This package processes no images and never will.** Image understanding is a
separate service, owned separately — see `AGENTS.md`. What lives here is the
contract the editor calls through, an HTTP client for that service, and a
deterministic stand-in so the editor can be built and evaluated before it exists.

## The three pieces

| | What it is |
|---|---|
| `VisionTool` | The Protocol the editor depends on. **One** operation, no state. |
| `HttpVisionTool` | Client for the real service. |
| `InventoryVisionTool` | In-process stand-in answering from the fixture's labels. |

The editor depends on the Protocol only, so swapping the placeholder for the real
service is a wiring change and nothing else.

## Why the stand-in is a lookup, not a constant

It answers from `fixtures/fleet-vehicle-return/inventory.yaml`, keyed by filename,
so every image gets its own correct label. That matters for one case in
particular:

```python
good, bad = await tool.build_inventory(
    [ImageRef(uri="1000040420.jpg"), ImageRef(uri="IMG_20260830_132755 (5).jpg")],
    [RequirementSpec(id="R-04", text="Two photographs of the headliner.",
                     constraint="camera position: between_front_seats")],
)
good.hits[0].constraint_ok   # True  — between the seats
bad.hits[0].constraint_ok    # False — beside the seat
```

Both photographs hit R-04; only one satisfies the pose constraint. If the stand-in
collapsed to a single answer, a derivative run would pass R-04 for the wrong
reason and the fixture would stop testing the thing it exists to test.

It also **cannot be wrong**, which makes it useless for measuring vision quality
and ideal for everything else: the editor, the applier and the evals become fully
deterministic, so a failing test means the editor is broken rather than that the
model had an off day. When the real service arrives, the same `inventory.yaml`
becomes the answer key it is scored against.

## Two distinctions the API insists on

**Unidentifiable is not unavailable.** An image the service looked at and could
not place comes back with empty `hits` — that is evidence, and the editor must
decide what it means for a requirement. A service that could not be reached
raises `VisionUnavailable`, which is infrastructure failure and must never be
recorded as a finding about the client's photographs.

**Constraint is per hit, not a global pose field.** Two photos can support the same
id and disagree on `constraint_ok`. Collapsing that loses R-04.

**Cropping is not part of this interface.** An earlier draft carried it, following req
13's wording. Nothing in the flow calls it — the editor decides whether a photograph
satisfies a requirement, and a crop does not change that answer.

## Configuration

`MFF_VISION_INVENTORY` overrides the inventory location. Otherwise the package
walks up from its own file looking for `fixtures/fleet-vehicle-return/`.
