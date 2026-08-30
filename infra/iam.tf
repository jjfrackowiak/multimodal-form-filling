resource "google_service_account" "cv" {
  account_id   = "cv-runtime"
  display_name = "CV Cloud Run runtime"
}

resource "google_service_account" "editor" {
  account_id   = "editor-runtime"
  display_name = "Editor Cloud Run runtime (invokes cv later)"
}

resource "google_project_iam_member" "cv_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.cv.email}"
}

resource "google_storage_bucket_iam_member" "cv_reads_files" {
  bucket = google_storage_bucket.files.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cv.email}"
}

resource "google_storage_bucket_iam_member" "editor_reads_files" {
  bucket = google_storage_bucket.files.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.editor.email}"
}

data "google_project" "this" {
  project_id = var.project_id
}

locals {
  cloudbuild_bucket = "${var.project_id}_cloudbuild"
  cloudbuild_sa     = "${data.google_project.this.number}@cloudbuild.gserviceaccount.com"
  compute_sa        = "${data.google_project.this.number}-compute@developer.gserviceaccount.com"
}

resource "google_artifact_registry_repository_iam_member" "cloudbuild_writes" {
  location   = google_artifact_registry_repository.app.location
  repository = google_artifact_registry_repository.app.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${local.cloudbuild_sa}"
}

resource "google_artifact_registry_repository_iam_member" "compute_writes" {
  location   = google_artifact_registry_repository.app.location
  repository = google_artifact_registry_repository.app.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${local.compute_sa}"
}

resource "google_storage_bucket_iam_member" "compute_cloudbuild_objects" {
  bucket = local.cloudbuild_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.compute_sa}"
}

resource "google_storage_bucket_iam_member" "cloudbuild_cloudbuild_objects" {
  bucket = local.cloudbuild_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.cloudbuild_sa}"
}

resource "google_project_iam_member" "compute_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${local.compute_sa}"
}
