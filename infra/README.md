# GCP — Terraform

Project `linen-badge-507111-r6`. Region `europe-central2`. Vertex for CV is `global`.

Source of truth for APIs, the files bucket, Firestore, Artifact Registry, runtime
service accounts, WIF for GitHub Actions, and Cloud Run **cv**. Editor and email
Cloud Run are created when `editor_image` / `email_image` are set.

No API keys. Cloud Run uses the runtime service account (ADC). GitHub Actions
impersonates `github-deploy` via Workload Identity Federation (no SA keys).

State lives in `gs://linen-badge-507111-r6-tfstate/infra/`. `*.tfstate` is gitignored.

## Canonical deploy

GitHub Actions: `.github/workflows/deploy-cv.yml`.

- Push to `main` (path-filtered) or **workflow_dispatch**.
- Cloud Build tags `…/cv:<git sha>`, then `terraform apply -var=cv_image=…`.
- Smoke: `GET /health` with an identity token.

`cv_image` is required. An apply that omits it errors instead of deleting Cloud Run.

## Laptop path

Needs `gcloud auth application-default login`. Always pass the image:

```bash
PROJECT=linen-badge-507111-r6
REGION=europe-central2
IMG=$REGION-docker.pkg.dev/$PROJECT/app/cv:$(git rev-parse HEAD)

gcloud builds submit --region="$REGION" --config docker/cloudbuild-cv.yaml \
  --gcs-source-staging-dir="gs://$PROJECT-build/source" \
  --gcs-log-dir="gs://$PROJECT-build/logs" \
  --substitutions=_IMAGE="$IMG" .
terraform -chdir=infra apply -var="cv_image=$IMG"
```

CV is private. The editor SA and `github-deploy` have `roles/run.invoker`. Smoke:

```bash
URL=$(terraform -chdir=infra output -raw cv_url)
# user accounts cannot pass --audiences; use:
gcloud run services proxy cv --region europe-central2
# then GET http://localhost:8080/health
```

## Bootstrap (already done on this project)

State was local, then migrated. Recreate only if you are standing up a new project:

1. Apply **without** a `backend "gcs"` block so Terraform can create
   `gs://<project>-tfstate` from local state.
2. Add the backend block in `versions.tf` and `terraform init -migrate-state`.
3. Confirm WIF: `terraform -chdir=infra output github_wif_provider`.

If Firestore `(default)` already exists:

```bash
terraform import google_firestore_database.default "projects/linen-badge-507111-r6/databases/(default)"
```

## Editor and email

`editor_image` / `email_image` default empty so an apply that only sets `cv_image`
does not create those services. `deploy-cv.yml` / `deploy-editor.yml` use
`-target` so they cannot destroy email. `count = 0` still destroys email on a
full apply with empty `email_image` or `imap_host` — laptop apply must pass
mailbox vars + `email_image` from gitignored `terraform.tfvars`. Email has
`deletion_protection = true`; turn it off before an intentional destroy.

Local compose runs CV in place of vision-stub. The editor calls `CV_URL` at slice time.
