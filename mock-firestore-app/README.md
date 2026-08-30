# Mock: job API + prepare function + 3 services

Local skeleton. No always-on polling worker.

**Product services (Cloud Run):**

| Service | Port | Owner | Now |
|---|---|---|---|
| `cv` | 8083 | Michal | Production tool: `POST /v1/inventory` |
| `email` | 8084 | Janek | Stub |
| `editor` | 8085 | Janek | Stub (`CV_URL=http://cv:8080`) |

**Job pipeline (file pointer + prepare only):**

| Piece | Port | Role |
|---|---|---|
| `api` | 8081 | Upload file, start job, read status |
| `fn-prepare` | 8082 | Confirm object exists in the bucket, set `prepared` |
| Firestore emulator | 8080 | Job records + `gs://` pointers |
| Fake GCS | 4443 | File bytes |

```
POST /files          → uploaded
POST /jobs/:id/start → queued, HTTP to fn-prepare
fn-prepare           → prepared  (does not call CV)
editor (when filled) → POST {CV_URL}/v1/inventory
```

CV is a **tool**, not a job worker. Contract: [`../cv/integration_guide_CV.md`](../cv/integration_guide_CV.md).

On GCP: `fn-prepare` is a Cloud Run **function** (or small service). `cv`, `email`, `editor` are Cloud Run **services**. Glue between prepare and the editor should be Cloud Tasks in production; locally it is HTTP.

## 1. Run locally

```bash
cd mock-firestore-app
docker compose up --build
```

Wait until the Firestore emulator is healthy (`Dev App Server is now running`).
CV needs ADC mounted (`~/.config/gcloud`) for Vertex.

## 2. Flow

```bash
curl -F "file=@README.md" http://localhost:8081/files
curl -X POST http://localhost:8081/jobs/JOB_ID/start
curl http://localhost:8081/jobs/JOB_ID

curl http://localhost:8083/health   # cv
curl http://localhost:8084/health   # email stub
curl http://localhost:8085/health   # editor stub (includes cv_url)
```

Call CV the way the editor will (photos must already be `gs://` JPEG/PNG/WebP):

```bash
curl -s http://localhost:8083/v1/inventory \
  -H 'content-type: application/json' \
  -d '{
    "images": [{"uri": "gs://mock-files/jobs/JOB_ID/images/front.jpg"}],
    "requirements": [
      {"id":"R-01","text":"A photograph of the front of the vehicle."}
    ]
  }'
```

Job after prepare (before editor exists):

```json
{
  "id": "...",
  "status": "prepared",
  "step": "prepare",
  "file": { "gsUri": "gs://mock-files/uploads/.../README.md" }
}
```

`status` / `step` tell you which unit failed.

## 3. Real GCP

Project: `all-things-agentic-google` / `linen-badge-507111-r6`.

Details: `gcp/DEPLOY.md`. Firestore Native + bucket + Artifact Registry. Do not put file bytes in Firestore. Grok is not logged into your GCP.
