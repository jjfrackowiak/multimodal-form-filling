# Cloud Run — CV tool

Canonical deploy is GitHub Actions (`.github/workflows/deploy-cv.yml`): Cloud Build
then Terraform. This file is the laptop equivalent.

Editor calls `POST /v1/inventory`. Runtime SA needs Vertex + Storage object viewer.
Contract: [`integration_guide_CV.md`](integration_guide_CV.md).

```bash
PROJECT=linen-badge-507111-r6
REGION=europe-central2
IMG=$REGION-docker.pkg.dev/$PROJECT/app/cv:$(git rev-parse HEAD)

gcloud builds submit --config docker/cloudbuild-cv.yaml --substitutions=_IMAGE="$IMG" .
terraform -chdir=infra apply -var="cv_image=$IMG"
```

`cv_image` is required. Do not set `ENABLE_JOB_ADAPTER` in production.
