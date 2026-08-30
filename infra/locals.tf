locals {
  bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.project_id}-files"
  cv_image    = var.cv_image
  ar_host     = "${var.region}-docker.pkg.dev"
}
