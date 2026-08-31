resource "google_cloud_run_v2_service" "cv" {
  name     = "cv"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  deletion_protection = false

  # API echoes a service-level scaling block we do not set; ignore so applies do not flap.
  lifecycle {
    ignore_changes = [scaling]
  }

  template {
    service_account                  = google_service_account.cv.email
    timeout                          = "900s"
    max_instance_request_concurrency = 4

    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    containers {
      image = var.cv_image

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
        name  = "CV_MAX_WORKERS"
        value = "1"
      }
      env {
        name  = "CV_MAX_IMAGES"
        value = "64"
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

resource "google_cloud_run_v2_service_iam_member" "editor_invokes_cv" {
  name     = google_cloud_run_v2_service.cv.name
  location = google_cloud_run_v2_service.cv.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.editor.email}"
}

resource "google_cloud_run_v2_service_iam_member" "github_invokes_cv" {
  name     = google_cloud_run_v2_service.cv.name
  location = google_cloud_run_v2_service.cv.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.github_deploy.email}"
}
