variable "project_id" {
  type        = string
  description = "GCP project. Vertex + Cloud Run + bucket live here."
  default     = "linen-badge-507111-r6"
}

variable "region" {
  type        = string
  description = "Cloud Run, Artifact Registry, and the files bucket."
  default     = "europe-central2"
}

variable "firestore_location" {
  type        = string
  description = "Firestore Native location (regional)."
  default     = "europe-central2"
}

variable "artifact_repo" {
  type        = string
  description = "Artifact Registry Docker repository id."
  default     = "app"
}

variable "bucket_name" {
  type        = string
  description = "Job files (.docx, photos). Empty = <project_id>-files."
  default     = ""
}

variable "cv_image" {
  type        = string
  description = "Full CV image URL (Artifact Registry). Required — omitting it errors instead of deleting Cloud Run."
}

variable "github_repository" {
  type        = string
  description = "GitHub repo allowed to impersonate github-deploy via WIF (owner/name)."
  default     = "jjfrackowiak/multimodal-form-filling"
}

variable "vertex_location" {
  type        = string
  description = "Vertex region for the CV Gemini client. global is what services/cv uses."
  default     = "global"
}
