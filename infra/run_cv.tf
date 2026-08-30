resource "google_cloud_run_v2_service" "cv" {
  count = local.cv_image == "" ? 0 : 1

  name     = "cv"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  deletion_protection = false

  template {
    service_account                  = google_service_account.cv.email
    timeout                          = "300s"
    max_instance_request_concurrency = 4

    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    containers {
      image = local.cv_image

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
        value = "12"
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
          path = "/healthz"
        }
        period_seconds    = 5
        failure_threshold = 12
      }
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "editor_invokes_cv" {
  count = local.cv_image == "" ? 0 : 1

  name     = google_cloud_run_v2_service.cv[0].name
  location = google_cloud_run_v2_service.cv[0].location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.editor.email}"
}
