# vision-stub

A placeholder for the image understanding service (req 13), which is owned
separately — see `AGENTS.md`. It exists so the editor has something real to call
while that service is built.

```
POST /v1/inventory   { images, requirements } -> { images: ImageAnalysis[] }
GET  /healthz
```

One operation. The service is told what is being looked for and answers with what each
image shows. Called once per job at ingest, so a whole submission is one round trip.

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

The real service implements the same single route and the same payloads. Nothing
in the editor changes — it depends on the `VisionTool` Protocol, not on this.

The real service is repo-root `cv/` (`POST /v1/inventory`, same `{images, requirements}`
payload). Hits + per-id `constraint_ok` replace a frozen `depicts` / `shot_from` enum.
