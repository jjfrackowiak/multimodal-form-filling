# Mock: Cloud Run (2 containers) + Firestore + bucket

Local skeleton for the GCP lane:

- **`api` container** — HTTP, file upload, writes a document to Firestore
- **`worker` container** — polls `queued` jobs, reads the file path from Firestore, “processes” the file from the bucket
- **Firestore** — holds records and **pointers** `gs://...`, not file bytes
- **bucket** — holds bytes

On GCP: API → Cloud Run **service**, worker → Cloud Run **worker pool** (or a service with `min-instances=1`), database → **Firestore**, files → **Cloud Storage**.

## 1. Run locally

You need Docker.

```bash
cd mock-firestore-app
docker compose up --build
```

Wait until the Firestore emulator is up (log: `Dev App Server is now running`). Compose waits on a healthcheck — without that the worker can hang on its first query and the job stays `queued`.

## 2. Flow

```bash
# upload a file → you get a job id
curl -F "file=@README.md" http://localhost:8081/files

# start processing (status: queued)
curl -X POST http://localhost:8081/jobs/JOB_ID/start

# wait 2–3 s, worker updates status
curl http://localhost:8081/jobs/JOB_ID
```

Expected document:

```json
{
  "id": "...",
  "status": "done",
  "file": {
    "bucket": "mock-files",
    "path": "uploads/.../README.md",
    "gsUri": "gs://mock-files/uploads/.../README.md",
    "originalName": "README.md",
    "sizeBytes": 1234
  },
  "result": { "bytes": 1234, "preview": "..." }
}
```

## 3. What lives where

| File | Role |
|---|---|
| `api/` | HTTP image |
| `worker/` | polling-loop image |
| `docker-compose.yml` | 4 services: Firestore emulator, fake GCS, api, worker |
| `gcp/SCHEMA.md` | document shape and what to carry to the real project |

## 4. Real GCP

Project: `all-things-agentic-google` / `linen-badge-507111-r6`.

1. Console: **Firestore** → create a database (Native mode, region e.g. `europe-central2`).
2. **Cloud Storage** → bucket e.g. `linen-badge-files`.
3. Build and push both images to Artifact Registry.
4. Deploy `api` as a Cloud Run service, `worker` as a second service (min instances 1) or a worker pool.
5. Env: `GCP_PROJECT`, `FIRESTORE_COLLECTION=jobs`, `BUCKET=...`
6. IAM: Cloud Run SA gets `roles/datastore.user` + `roles/storage.objectAdmin`.
7. Add Janek in **IAM & Admin** (not via this chat — Grok is not logged into your GCP).

Command details: `gcp/DEPLOY.md`.
