locals {
  bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.project_id}-files"
  ar_host     = "${var.region}-docker.pkg.dev"
}
