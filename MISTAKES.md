# Mistakes

## 2026-08-30 — CV look-fors come from the manifest

**What went wrong:** `schema.py` froze 11 `depicts` values from the Qashqai fixture. A new manifest (VIN plate, 4 tyres, …) would not change CV behaviour.

**Prevention:** Checklist is `expected_requirements.yaml`. If every requirement already has `id` + `source_span`, that *is* the useful part of the manifest — do not require `manifest.txt`. Read the raw manifest only when those fields are missing.


## 2026-08-30 — GCP is Terraform later

**Note (not a bug yet):** User wants GCP as **code (Terraform)**. Do not design around permanent console/`gcloud` snowflakes. `DEPLOY.md` is temporary. When provisioning Cloud Run / Firestore / bucket / IAM / Vertex, add `.tf` in-repo.


## 2026-08-30 — CV is not inside the editor service

**What went wrong:** Talked about B11 as `services/editor-service/.../tools/vision` (`VisionTool` living in the editorial process). That matches Janek’s implementation plan, not how we are building it.

**Prevention:** The CV module is a **separate service** (`cv/`). The editor may hold a thin HTTP client; it must not contain crop/understand/process. Do not land vision under `editor-service`. First CV deliverable is generating `inventory.yaml`; cropping is deferred. Fixture YAML stubs evals until generate+eval is green.
