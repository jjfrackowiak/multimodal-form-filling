# vision-stub

A placeholder for the image understanding service (req 13), which is owned
separately — see `AGENTS.md`. It exists so the editor has something real to call
while that service is built.

```
POST /v1/describe        ImageRef              -> ImageAnalysis
POST /v1/describe:batch  list[ImageRef]        -> list[ImageAnalysis]
POST /v1/crop            ImageRef + BoundingBox -> ImageRef
GET  /healthz
```

It answers from the fleet fixture's labelled inventory and **performs no image
processing**. `/healthz` reports `"implementation": "placeholder"` so a green
healthcheck is never mistaken for working image understanding.

## Running it

```bash
uvicorn vision_stub.main:app --port 8099
curl -s -X POST localhost:8099/v1/describe \
  -H 'content-type: application/json' \
  -d '{"ref":{"uri":"gs://bucket/jobs/x/images/1000040420.jpg"}}'
```

## Replacing it

The real service implements the same four routes and the same payloads. Nothing
in the editor changes — it depends on the `VisionTool` Protocol, not on this.

Two things to agree with the owner before that happens:

1. **The payload shapes**, which are defined in `mff_vision.models`. They were
   written from the editor's needs, not from what a CV pipeline naturally emits,
   so they are a proposal rather than a decision.
2. **Whether `shot_from` is a closed vocabulary.** The fixture uses
   `between_front_seats` and `beside_seat`. If it stays free text, the editor has
   to interpret strings it has never seen, and R-04 stops being decidable.
