resource "google_cloud_run_v2_service" "editor" {
  count    = var.editor_image != "" ? 1 : 0
  name     = "editor"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  deletion_protection = false

  lifecycle {
    ignore_changes = [scaling]
  }

  template {
    service_account                  = google_service_account.editor.email
    timeout                          = "600s"
    max_instance_request_concurrency = 2

    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    containers {
      image = var.editor_image

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.vertex_location
      }
      env {
        name  = "GOOGLE_GENAI_USE_ENTERPRISE"
        value = "true"
      }
      env {
        name  = "CV_URL"
        value = google_cloud_run_v2_service.cv.uri
      }

      ports {
        container_port = 8080
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        period_seconds    = 5
        failure_threshold = 12
      }
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "email_invokes_editor" {
  count    = var.editor_image != "" ? 1 : 0
  name     = google_cloud_run_v2_service.editor[0].name
  location = google_cloud_run_v2_service.editor[0].location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.email.email}"
}

resource "google_cloud_run_v2_service_iam_member" "github_invokes_editor" {
  count    = var.editor_image != "" ? 1 : 0
  name     = google_cloud_run_v2_service.editor[0].name
  location = google_cloud_run_v2_service.editor[0].location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.github_deploy.email}"
}
