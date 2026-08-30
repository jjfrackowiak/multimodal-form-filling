# Mock: job API + prepare function + 3 services

Local skeleton. No always-on polling worker.

**Product services (Cloud Run):**

| Service | Port | Owner | Now |
|---|---|---|---|
| `cv` | 8083 | Michal | Dummy process step (later real image tools) |
| `email` | 8084 | Janek | Stub |
| `editor` | 8085 | Janek | Stub |

**Job pipeline:**

| Piece | Port | Role |
|---|---|---|
| `api` | 8081 | Upload file, start job, read status |
| `fn-prepare` | 8082 | Confirm object exists in the bucket, set `prepared`, call CV |
| Firestore emulator | 8080 | Job records + `gs://` pointers |
| Fake GCS | 4443 | File bytes |

```
POST /files        → uploaded
POST /jobs/:id/start → queued, HTTP to fn-prepare
fn-prepare         → prepared, HTTP to cv
cv /process        → processing → done
```

On GCP: `fn-prepare` is a Cloud Run **function** (or small service). `cv`, `email`, `editor` are Cloud Run **services**. Glue between steps should be Cloud Tasks in production; locally it is HTTP.

## 1. Run locally

```bash
cd mock-firestore-app
docker compose up --build
```

Wait until the Firestore emulator is healthy (`Dev App Server is now running`).

## 2. Flow

```bash
curl -F "file=@README.md" http://localhost:8081/files
curl -X POST http://localhost:8081/jobs/JOB_ID/start
curl http://localhost:8081/jobs/JOB_ID

curl http://localhost:8083/health   # cv
curl http://localhost:8084/health   # email stub
curl http://localhost:8085/health   # editor stub
```

Expected job when finished:

```json
{
  "id": "...",
  "status": "done",
  "step": "process",
  "file": {
    "gsUri": "gs://mock-files/uploads/.../README.md"
  },
  "result": { "bytes": 1234, "preview": "..." }
}
```

`status` / `step` tell you which unit failed (`prepare` vs `process`).

## 3. Real GCP

Project: `all-things-agentic-google` / `linen-badge-507111-r6`.

Details: `gcp/DEPLOY.md`. Firestore Native + bucket + Artifact Registry. Do not put file bytes in Firestore. Grok is not logged into your GCP.
