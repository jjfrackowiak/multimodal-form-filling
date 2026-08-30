# Mistakes

## 2026-08-30 — CV is not inside the editor service

**What went wrong:** Talked about B11 as `services/editor-service/.../tools/vision` (`VisionTool` living in the editorial process). That matches Janek’s implementation plan, not how we are building it.

**Prevention:** The CV module is a **separate service** (`cv/`). The editor may hold a thin HTTP client; it must not contain crop/understand/process. Do not land vision under `editor-service`. First CV deliverable is generating `inventory.yaml`; cropping is deferred. Fixture YAML stubs evals until generate+eval is green.
