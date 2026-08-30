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

output "cv_image_prefix" {
  value = "${local.ar_host}/${var.project_id}/${var.artifact_repo}/cv"
}

output "cv_image" {
  value = var.cv_image
}

output "cv_runtime_sa" {
  value = google_service_account.cv.email
}

output "editor_runtime_sa" {
  value = google_service_account.editor.email
}

output "cv_url" {
  value = google_cloud_run_v2_service.cv.uri
}

output "github_deploy_sa" {
  value = google_service_account.github_deploy.email
}

output "github_wif_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}
