# Deploy na prawdziwy projekt (nie emulator)

Projekt ze screena: `linen-badge-507111-r6` (`all-things-agentic-google`).

Grok **nie jest** zalogowany do Twojego GCP. Te komendy odpalasz u siebie
po `gcloud auth login` i `gcloud config set project linen-badge-507111-r6`.

```bash
PROJECT=linen-badge-507111-r6
REGION=europe-central2
REPO=app
BUCKET=${PROJECT}-files

gcloud services enable run.googleapis.com firestore.googleapis.com \
  storage.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION || true
gcloud storage buckets create gs://$BUCKET --location=$REGION || true

# Firestore Native — raz, z konsoli albo:
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

Potem IAM na default compute SA (albo osobne SA):

- `roles/datastore.user`
- `roles/storage.objectAdmin`

Znajomy: IAM → Grant access → `user:email@...` → `roles/editor` (hackathon)
albo ciaśniejsze role Cloud Run / Firestore / Storage.
