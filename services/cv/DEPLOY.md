# Cloud Run — CV tool

Canonical deploy is Terraform in `infra/`. This file is the image build only.

Editor calls `POST /v1/inventory`. Runtime SA needs Vertex + Storage object viewer.
Contract: [`integration_guide_CV.md`](integration_guide_CV.md).

```bash
PROJECT=linen-badge-507111-r6
REGION=europe-central2
IMG=$REGION-docker.pkg.dev/$PROJECT/app/cv:v1

# from repo root, after `terraform -chdir=infra apply`
gcloud builds submit --tag "$IMG" -f docker/cv.Dockerfile .
terraform -chdir=infra apply -var="cv_image=$IMG"
```

Do not set `ENABLE_JOB_ADAPTER` in production.
