# CV module — integration guide

This is the production contract for the image / CV tool (req. 13). The AI editor
calls it as a **Cloud Run HTTP tool**. Vision does **not** live inside the
editor service.

Canonical code: `cv/`. Deploy: `cv/DEPLOY.md`. In-process CLI: `python -m cv`.

## What it does

Given a **checklist** (discrete requirements with ids) and **photos already in
GCS**, it returns an **inventory**: for each unique photo, which checklist ids
it actually supports, plus generic visual findings (damage, lamps, readings,
plates, …). Exact byte-duplicates are collapsed.

It does **not**:

- Crop (deferred)
- Parse email or the Word artifact
- Store job state in Firestore
- Accept image bytes in the HTTP body
- Convert HEIC / HEIF (clients upload JPEG, PNG, or WebP)

The editor owns when to call it, what to do with the inventory, and how that
feeds comments / verdicts.

## How it works

```
editor (or any caller with run.invoker)
  POST /v1/inventory  { images: [{uri}], requirements: [{id, text, constraint?}] }
    → CV downloads gs:// objects
    → downscales each frame (max edge 1536, JPEG q80)
    → sha256-dedupes
    → parallel Vertex Gemini (gemini-2.5-flash, ADC, location=global)
    → JSON Inventory
```

One Vertex call per unique image, up to `CV_MAX_WORKERS` (default 12) in
parallel. 429s are retried. Wall time for ~15 photos is a few seconds when
Vertex is warm; Cloud Run timeout is 300s.

Same logic is `cv.build_inventory(paths, checklist)` for local/CLI. Production
callers must use HTTP so the editor stays free of Vertex/Pillow.

## Endpoint

| | |
|---|---|
| Method | `POST /v1/inventory` |
| Auth (prod) | Cloud Run IAM. Unauthenticated denied. Caller SA needs `roles/run.invoker`. |
| Auth (compose) | none — `http://cv:8080` on the docker network |
| Content-Type | `application/json` |
| Body limit | JSON only. Photos are GCS objects, not multipart. |
| Timeout | 300s (match Cloud Run `--timeout`) |
| Health | `GET /health` — no Vertex call |
| OpenAPI | `GET /docs` |

Do **not** call `POST /process`. That exists only when `ENABLE_JOB_ADAPTER=1`
for the local mock job skeleton. Production must leave that unset.

Python:

```python
from mff_vision import HttpVisionTool, ImageRef, RequirementSpec

cv = HttpVisionTool(base_url=CV_URL)  # identity token on *.run.app
images = await cv.build_inventory(
    [ImageRef(uri="gs://bucket/jobs/<id>/images/front.jpg")],
    [RequirementSpec(id="R-01", text="A photograph of the front of the vehicle.")],
)
```

Same payload from `cv.CvClient`. Do not import `cv.pipeline` / Vertex from the editor.

## Expected inputs

### `requirements` (required)

Same as `mff_contracts.RequirementSpec`: `id`, `text`, optional `constraint`.
`text` is the look-for. Do not send the raw email quote.

| Field | Required | Notes |
|---|---|---|
| `requirements` | yes, ≥ 1 | |
| `requirements[].id` | yes | Stable, unique (`R-01`, …) |
| `requirements[].text` | yes | What to look for (already parsed) |
| `requirements[].constraint` | no | Extra pixel check (`between_front_seats`, …) |

If every item has `id` + `text`, omit `manifest`. The tool 400s only when ids/text
are incomplete and `manifest` is empty.

### Photos

Always **pointers**, never bytes:

| Field | Use |
|---|---|
| `images` | `{ "uri": "gs://bucket/object" }` list (editor interface) |
| `image_prefix` | `gs://bucket/jobs/<id>/images/` — extra objects under the prefix |

At least one of the two is required. Prefix listing **skips** non-images.
Explicit URIs that are not images **400**.

**Accepted:** `.jpg` `.jpeg` `.png` `.webp`  
**Rejected:** `.heic` `.heif` and everything else. No server-side conversion.

Cap: `CV_MAX_IMAGES` (default 64). Duplicate URIs are dropped.

Objects must be readable by the CV runtime service account
(`roles/storage.objectViewer` is enough).

### Example request

```json
{
  "images": [{"uri": "gs://linen-badge-507111-r6-files/jobs/abc/images/front.jpg"}],
  "requirements": [
    {
      "id": "R-01",
      "text": "A photograph of the front of the vehicle."
    }
  ]
}
```

## Expected outputs

`200` body:

```json
{
  "images": [
    {
      "file": "front.jpg",
      "uri": "gs://bucket/jobs/abc/images/front.jpg",
      "hits": [
        {
          "id": "R-01",
          "constraint_ok": null,
          "constraint_evidence": null
        }
      ],
      "note": "front three-quarter of a silver hatchback",
      "findings": [
        { "what": "damage", "value": "scuff on front bumper", "evidence": "lower right" }
      ],
      "exact_duplicate_of": null
    }
  ],
  "exact_duplicate_pairs": [["front.jpg", "front-copy.jpg"]],
  "duration_seconds": 18.4,
  "model": "gemini-2.5-flash",
  "project": "linen-badge-507111-r6"
}
```

| Field | Meaning |
|---|---|
| `images[].file` | Basename after download (collisions get `_1` suffix) |
| `images[].uri` | Original `gs://` so the editor can join back to the blob |
| `images[].hits` | Checklist ids **this frame actually supports** (0..n). Unknown ids stripped. |
| `hits[].constraint_ok` | Only if that id has a `constraint`; else `null`. Per-id, not one global flag. |
| `images[].findings` | Generic observations. Not a frozen odometer/plate/seat schema. |
| `exact_duplicate_pairs` | `[canonical_name, extra_name]` for sha256 matches. Only the canonical is labeled. |

`images` is index-aligned with the request. Correlate with `uri`. Byte-duplicates share a label.

Findings are hints for the editor, not a form. The editor decides verdicts.

## Errors

| HTTP | When |
|---|---|
| 400 | Missing images, empty requirements, bad `gs://`, HEIC/non-image, too many images, incomplete ids/text without `manifest` |
| 404 | `POST /process` in production (adapter off) |
| 502 | GCS download/list failed, or Vertex failed after retries |
| 422 | JSON does not match the request schema |

`GET /health` is 200 if the process is up. It does not prove Vertex/GCS.

Every response includes `x-request-id` (echoed from the request header if sent).

## Auth, IAM, env (GCP)

Project: `linen-badge-507111-r6`. Region for Cloud Run: `europe-central2`.
Vertex location: `global`.

**CV runtime SA**

- `roles/aiplatform.user`
- `roles/storage.objectViewer` (objectAdmin only if this service ever writes)

**Editor runtime SA**

- `roles/run.invoker` on service `cv`
- `roles/storage.objectViewer` if the editor also reads the same objects

**Env on Cloud Run `cv`**

| Name | Default | Purpose |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | `linen-badge-507111-r6` | Vertex + GCS |
| `GOOGLE_CLOUD_LOCATION` | `global` | Vertex |
| `CV_MODEL` | `gemini-2.5-flash` | |
| `CV_MAX_WORKERS` | `12` | Parallel Vertex calls (one per image) |
| `CV_MAX_IMAGES` | `64` | Hard cap per request |
| `PORT` | `8080` | Cloud Run sets this |

Do **not** set `ENABLE_JOB_ADAPTER`. Do **not** put API keys in env; Vertex
uses ADC on the runtime SA.

Suggested Cloud Run: `--no-allow-unauthenticated --memory 2Gi --cpu 2 --timeout 300 --concurrency 4`.

The editor sets `CV_URL` to the Cloud Run URL (`https://cv-….run.app`).
`CvClient` fetches an identity token with that URL as audience.

## How this fits the rest of the app

```
email (Janek)  →  parse attachments, put photos in GCS, hand off job
editor (Janek) →  for the image slice: CvClient.inventory(...)
cv  (Michal)   →  inventory JSON
editor         →  comments / verdicts on the Word artifact
```

`fn-prepare` in the mock app only checks that a GCS object exists. It does
**not** call CV. CV is a tool, not a job worker.

Suggested object layout (not enforced by CV):

```
gs://<project>-files/jobs/<job_id>/images/<name>.jpg
```

Then the editor can pass `image_prefix: "gs://<project>-files/jobs/<job_id>/images/"`.

Firestore: CV does not read or write it. Job records stay with api / editor.

## Local mock (`mock-firestore-app`)

```bash
cd mock-firestore-app && docker compose up --build
curl -s http://localhost:8083/health
```

Compose builds `cv/Dockerfile` from the repo root, mounts ADC for Vertex, and
sets `CV_URL=http://cv:8080` on the **editor** stub. The editor `/runs`
endpoint is still 501 — when it is filled in, that env is already the tool
base URL. Compose does not require identity tokens.

Fake GCS (`STORAGE_EMULATOR_HOST`) is used for `gs://` materialize. Vertex
still hits the real project via ADC.

## Local CLI (no Cloud Run)

```bash
python -m cv fixtures/fleet-vehicle-return/images \
  --requirements fixtures/fleet-vehicle-return/expected_requirements.yaml \
  --out /tmp/inventory.yaml
```

Needs ADC (`gcloud auth application-default login`) on project
`linen-badge-507111-r6`.

Offline tests (no Vertex): `python -m cv.test_offline`

## Latency / cost notes

- Parallelism is the lever, not a larger Gemini.
- Stick to `gemini-2.5-flash` unless quality is measured again.
- Prefix listing + download happens before Vertex; huge prefixes waste time
  even if later capped.
- Identical bytes are labeled once.

## Ownership

Michal: this service, Vertex, GCS read path, Cloud Run deploy of `cv`.
Janek: email + editor; thin HTTP client only.
Cropping and Terraform land later; this HTTP contract should stay stable.
