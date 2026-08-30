resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = var.artifact_repo
  description   = "Application images (cv, later email/editor)."
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}
