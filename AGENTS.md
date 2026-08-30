# Agent notes

Repo language is **English** (docs, comments, commits, chat).

Two owners. Do not cross the line unless asked.

## Michal (`michaluppal`)

- Image / CV tools (req. 13): image processing, image understanding, cropping.
- GCP deployment.

**CV is its own service** (`cv` / Cloud Run). It is **not** a package inside the AI editor. The editor calls it over HTTP (BlobRef in, labels/crops out). Do not implement `VisionTool` under `editor-service`.

Stay here. Interfaces the editor will call should be small, documented, and stable.

`services/email` and `services/editor` are **stubs** (health + 501). Do not fill in Janek’s logic unless asked.

## Janek (`jjfrackowiak`)

- Email service (Part 1).
- AI editor (Part 2): handover, external document state, line-targeted edits, comments, Pydantic validation, retries.

Do not implement or refactor those unless explicitly requested.
