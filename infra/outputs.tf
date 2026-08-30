output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "bucket" {
  value = google_storage_bucket.files.name
}

output "artifact_registry" {
  value = "${local.ar_host}/${var.project_id}/${var.artifact_repo}"
}

output "cv_image_suggested" {
  value = "${local.ar_host}/${var.project_id}/${var.artifact_repo}/cv:v1"
}

output "cv_runtime_sa" {
  value = google_service_account.cv.email
}

output "editor_runtime_sa" {
  value = google_service_account.editor.email
}

output "cv_url" {
  value       = try(google_cloud_run_v2_service.cv[0].uri, null)
  description = "Set after the first image build + apply with cv_image."
}
