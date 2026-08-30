# Deploy to a real project (not the emulator)

**Future note:** production GCP should be **Terraform** in this repo, not a one-off `gcloud` script. The commands below are a bootstrap cheat sheet until that exists.

Project: `linen-badge-507111-r6` (`all-things-agentic-google`).

Grok is **not** logged into your GCP. Run these locally after
`gcloud auth login` and `gcloud config set project linen-badge-507111-r6`.

There is no always-on worker. Deploy:

- Cloud Run **function** (or small service): `fn-prepare`
- Cloud Run **services**: `cv`, `email`, `editor`, plus demo `api`

Between steps, use **Cloud Tasks** (retry the next HTTP handler). Local compose uses plain HTTP.

```bash
PROJECT=linen-badge-507111-r6
REGION=europe-central2
REPO=app
BUCKET=${PROJECT}-files

gcloud services enable run.googleapis.com firestore.googleapis.com \
  storage.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  cloudtasks.googleapis.com

gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION || true
gcloud storage buckets create gs://$BUCKET --location=$REGION || true

# Firestore Native — once, from the console or:
# gcloud firestore databases create --location=$REGION

API_IMG=$REGION-docker.pkg.dev/$PROJECT/$REPO/api:v1
PREPARE_IMG=$REGION-docker.pkg.dev/$PROJECT/$REPO/fn-prepare:v1
CV_IMG=$REGION-docker.pkg.dev/$PROJECT/$REPO/cv:v1
EMAIL_IMG=$REGION-docker.pkg.dev/$PROJECT/$REPO/email:v1
EDITOR_IMG=$REGION-docker.pkg.dev/$PROJECT/$REPO/editor:v1

gcloud builds submit ./api --tag $API_IMG
gcloud builds submit ./fn-prepare --tag $PREPARE_IMG
# from repo root:
gcloud builds submit --tag $CV_IMG -f docker/cv.Dockerfile .
gcloud builds submit ./services/email --tag $EMAIL_IMG
gcloud builds submit ./services/editor --tag $EDITOR_IMG

# CV is the editor's tool, not a job worker. See services/cv/DEPLOY.md.
gcloud run deploy cv \
  --image $CV_IMG \
  --region $REGION \
  --no-allow-unauthenticated \
  --memory 2Gi --cpu 2 --timeout 300 --concurrency 4 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global,CV_MAX_WORKERS=12

# Then fn-prepare, api, stubs.
# Editor: CV_URL=<cv Cloud Run URL>
# api:    PREPARE_URL=<fn-prepare URL>
# fn-prepare does not call CV.
```

IAM:

- CV runtime SA: `roles/aiplatform.user`, `roles/storage.objectViewer`
- Editor runtime SA: `roles/run.invoker` on `cv`; `roles/storage.objectViewer` if it reads blobs
- api / fn-prepare: `roles/datastore.user`, `roles/storage.objectAdmin`

Teammate: IAM → Grant access → `user:email@...` → `roles/editor` (hackathon)
or tighter Cloud Run / Firestore / Storage roles.
