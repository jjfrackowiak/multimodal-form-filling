# Agent notes

Repo language is **English** (docs, comments, commits, chat).

Two owners. Do not cross the line unless asked.

## Michal (`michaluppal`)

- Image / CV tools (req. 13): image processing, image understanding, cropping.
- GCP deployment.

**CV is its own service** (`cv/`). It is **not** inside the AI editor. For now the deliverable is **`inventory.yaml`** (depicts + headliner `shot_from`). Cropping is deferred. Duplicates are sha256, not the model.

Stay here. Interfaces the editor will call should be small, documented, and stable.

`services/email` and `services/editor` are **stubs** (health + 501). Do not fill in Janek’s logic unless asked.

## Janek (`jjfrackowiak`)

- Email service (Part 1).
- AI editor (Part 2): handover, external document state, line-targeted edits, comments, Pydantic validation, retries.

Do not implement or refactor those unless explicitly requested.
