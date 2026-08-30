# Mistakes

## 2026-08-30 — CV is not inside the editor service

**What went wrong:** Talked about B11 as `services/editor-service/.../tools/vision` (`VisionTool` living in the editorial process). That matches Janek’s implementation plan, not how we are building it.

**Prevention:** The CV module is a **separate service** (Cloud Run `cv`). The editor may hold a thin HTTP client / protocol; it must not contain crop/understand/process implementations. Do not land vision code under `editor-service`. Fixture `inventory.yaml` stubs *evals* until that service exists — it is not an in-editor fake.
