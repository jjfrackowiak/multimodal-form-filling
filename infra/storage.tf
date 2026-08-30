resource "google_storage_bucket" "files" {
  name                        = local.bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  depends_on                  = [google_project_service.apis]
}

resource "google_storage_bucket" "tfstate" {
  name                        = "${var.project_id}-tfstate"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  depends_on                  = [google_project_service.apis]

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Cloud Build's default ${project}_cloudbuild bucket is in US and grants
# legacyBucketOwner only to project editors. github-deploy is neither, so
# `gcloud builds submit` 403s. Stage source in-region instead.
resource "google_storage_bucket" "build" {
  name                        = "${var.project_id}-build"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  depends_on                  = [google_project_service.apis]
}
