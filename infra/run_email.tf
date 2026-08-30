resource "google_cloud_run_v2_service" "email" {
  count    = var.email_image != "" && var.editor_image != "" ? 1 : 0
  name     = "email"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  deletion_protection = false

  lifecycle {
    ignore_changes = [scaling]
  }

  template {
    service_account                  = google_service_account.email.email
    timeout                          = "900s"
    max_instance_request_concurrency = 1

    scaling {
      min_instance_count = 1
      max_instance_count = 2
    }

    containers {
      image = var.email_image

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "MFF_GCS_BUCKET"
        value = google_storage_bucket.files.name
      }
      env {
        name  = "EDITOR_SERVICE_URL"
        value = google_cloud_run_v2_service.editor[0].uri
      }
      env {
        name  = "IMAP_HOST"
        value = var.imap_host
      }
      env {
        name  = "IMAP_PORT"
        value = tostring(var.imap_port)
      }
      env {
        name  = "IMAP_FOLDER"
        value = var.imap_folder
      }
      env {
        name  = "IMAP_USER"
        value = var.imap_user
      }
      env {
        name  = "IMAP_PASSWORD"
        value = var.imap_password
      }
      env {
        name  = "IMAP_USE_TLS"
        value = var.imap_use_tls ? "true" : "false"
      }
      env {
        name  = "SMTP_HOST"
        value = var.smtp_host
      }
      env {
        name  = "SMTP_PORT"
        value = tostring(var.smtp_port)
      }
      env {
        name  = "SMTP_USER"
        value = var.smtp_user
      }
      env {
        name  = "SMTP_PASSWORD"
        value = var.smtp_password
      }
      env {
        name  = "SMTP_USE_TLS"
        value = var.smtp_use_tls ? "true" : "false"
      }
      env {
        name  = "MAIL_FROM"
        value = var.mail_from
      }
      env {
        name  = "MAIL_FROM_NAME"
        value = "Form Validation"
      }
      env {
        name  = "ALLOWED_SENDERS"
        value = var.allowed_senders
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

resource "google_cloud_run_v2_service_iam_member" "github_invokes_email" {
  count    = var.email_image != "" && var.editor_image != "" ? 1 : 0
  name     = google_cloud_run_v2_service.email[0].name
  location = google_cloud_run_v2_service.email[0].location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.github_deploy.email}"
}
