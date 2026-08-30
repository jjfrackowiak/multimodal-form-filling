# Agent notes

Repo language is **English** (docs, comments, commits, chat).

Two owners. Do not cross the line unless asked.

## Michal (`michaluppal`)

- Image / CV tools (req. 13): image processing, image understanding, cropping.
- GCP deployment. **Future: Terraform (infrastructure as code)** — Cloud Run, Firestore, GCS, IAM, Vertex access. Do not treat `gcloud` console clicks or `gcp/DEPLOY.md` as the long-term source of truth. No Terraform tree yet; when we provision for real, start with `.tf` in-repo.

**CV** is Cloud Run `POST /v1/inventory` (`cv/` package, parallel Vertex). Always: checklist + `gs://` JPEG/PNG/WebP. Raw manifest only if ids/`source_span` missing. Cropping deferred. Not HEIC. Contract: `cv/integration_guide_CV.md`.

Stay here. Interfaces the editor will call should be small, documented, and stable.

`services/email` and `services/editor` are **stubs** (health + 501). Do not fill in Janek’s logic unless asked.

## Janek (`jjfrackowiak`)

- Email service (Part 1).
- AI editor (Part 2): handover, external document state, line-targeted edits, comments, Pydantic validation, retries.

Do not implement or refactor those unless explicitly requested.
