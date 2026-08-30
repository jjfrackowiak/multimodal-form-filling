# Cloud Run — CV tool

Editor calls `POST /v1/inventory` (JSON). Runtime SA needs Vertex + Storage.
Contract: [`integration_guide_CV.md`](integration_guide_CV.md).

Build from **repo root** (Dockerfile copies `cv/`):

```bash
PROJECT=linen-badge-507111-r6
REGION=europe-central2
REPO=app
IMG=$REGION-docker.pkg.dev/$PROJECT/$REPO/cv:v1

gcloud builds submit --tag "$IMG" -f cv/Dockerfile .

gcloud run deploy cv \
  --image "$IMG" \
  --region "$REGION" \
  --no-allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --concurrency 4 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global,CV_MAX_WORKERS=12,CV_MAX_IMAGES=64
```

Runtime SA:

- `roles/aiplatform.user`
- `roles/storage.objectViewer`

Editor SA: `roles/run.invoker` on this service. Set `CV_URL` to the Cloud Run URL.

Do not set `ENABLE_JOB_ADAPTER` in production. That path is only for a local
mock that still POSTs `{jobId}` at `/process`.
