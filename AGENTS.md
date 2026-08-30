# Agent notes

Repo language is **English** (docs, comments, commits, chat).

Two owners. Do not cross the line unless asked.

## Michal (`michaluppal`)

- Image / CV tools (req. 13): image processing, image understanding, cropping.
- GCP deployment. **Future: Terraform (infrastructure as code)** — Cloud Run, Firestore, GCS, IAM, Vertex access. Do not treat `gcloud` console clicks or `gcp/DEPLOY.md` as the long-term source of truth. No Terraform tree yet; when we provision for real, start with `.tf` in-repo.

**CV** is `cv.build_inventory` (parallel Vertex). Always: checklist yaml + photos. Raw manifest only if ids/`source_span` missing. Cropping deferred.

Stay here. Interfaces the editor will call should be small, documented, and stable.

`services/email` and `services/editor` are **stubs** (health + 501). Do not fill in Janek’s logic unless asked.

## Janek (`jjfrackowiak`)

- Email service (Part 1).
- AI editor (Part 2): handover, external document state, line-targeted edits, comments, Pydantic validation, retries.

Do not implement or refactor those unless explicitly requested.
