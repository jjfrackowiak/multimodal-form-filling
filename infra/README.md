# GCP — Terraform

Project `linen-badge-507111-r6`. Region `europe-central2`. Vertex for CV is `global`.

This is the source of truth for APIs, the files bucket, Firestore, Artifact Registry,
runtime service accounts, and Cloud Run **cv**. Email and editor images wait until those
services have a `/healthz`; their SAs exist so IAM is ready.

No API keys. Cloud Run uses the runtime service account (ADC).

## 1. Shared infra (no image yet)

Needs `gcloud auth application-default login` and a billing-enabled project.

```bash
cd infra
terraform init
terraform apply
```

Creates: enabled APIs, `gs://<project>-files`, Firestore Native, Artifact Registry
`app`, `cv-runtime` and `editor-runtime` SAs.

If Firestore `(default)` already exists:

```bash
terraform import google_firestore_database.default "projects/linen-badge-507111-r6/databases/(default)"
```

## 2. Build CV and attach Cloud Run

```bash
# from repo root
PROJECT=linen-badge-507111-r6
REGION=europe-central2
IMG=$REGION-docker.pkg.dev/$PROJECT/app/cv:v1

gcloud builds submit --tag "$IMG" -f docker/cv.Dockerfile .

cd infra
terraform apply -var="cv_image=$IMG"
```

CV is private. The editor SA has `roles/run.invoker`. Smoke from your laptop:

```bash
gcloud run services proxy cv --region europe-central2
# then POST http://localhost:8080/v1/inventory  (see services/cv/integration_guide_CV.md)
```

Or `gcloud auth print-identity-token` against the Cloud Run URL as audience.

## 3. Not in this stack yet

- email-service / editor-service Cloud Run (empty skeletons)
- Cloud Tasks between steps
- pointing `compose.yaml` `VISION_SERVICE_URL` at this service (local editor still uses vision-stub)
