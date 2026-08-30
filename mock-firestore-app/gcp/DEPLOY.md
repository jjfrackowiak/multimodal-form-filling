# Deploy to a real project (not the emulator)

Project: `linen-badge-507111-r6` (`all-things-agentic-google`).

Grok is **not** logged into your GCP. Run these locally after
`gcloud auth login` and `gcloud config set project linen-badge-507111-r6`.

```bash
PROJECT=linen-badge-507111-r6
REGION=europe-central2
REPO=app
BUCKET=${PROJECT}-files

gcloud services enable run.googleapis.com firestore.googleapis.com \
  storage.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION || true
gcloud storage buckets create gs://$BUCKET --location=$REGION || true

# Firestore Native — once, from the console or:
# gcloud firestore databases create --location=$REGION

API_IMG=$REGION-docker.pkg.dev/$PROJECT/$REPO/api:v1
WORKER_IMG=$REGION-docker.pkg.dev/$PROJECT/$REPO/worker:v1

gcloud builds submit ./api --tag $API_IMG
gcloud builds submit ./worker --tag $WORKER_IMG

gcloud run deploy mock-api \
  --image $API_IMG \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT=$PROJECT,BUCKET=$BUCKET,COLLECTION=jobs

gcloud run deploy mock-worker \
  --image $WORKER_IMG \
  --region $REGION \
  --no-allow-unauthenticated \
  --min-instances 1 \
  --no-cpu-throttling \
  --set-env-vars GCP_PROJECT=$PROJECT,BUCKET=$BUCKET,COLLECTION=jobs
```

Then IAM on the default compute SA (or a dedicated SA):

- `roles/datastore.user`
- `roles/storage.objectAdmin`

Teammate: IAM → Grant access → `user:email@...` → `roles/editor` (hackathon)
or tighter Cloud Run / Firestore / Storage roles.
