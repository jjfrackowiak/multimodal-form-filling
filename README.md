# Multimodal Form Filling

Email-driven form validation / composition. Spec: [`multimodal-form-filling/email-form-validation-requirements.pdf`](multimodal-form-filling/email-form-validation-requirements.pdf) (30 August 2026).

## Ownership

| Area | Owner | Spec |
|------|--------|------|
| Email service (intake, confirmation / rejection replies, handoff) | Janek | Part 1 |
| AI editor (scoped agent runs, document state, line edits, Pydantic retry) | Janek | Part 2 |
| Image / CV — Cloud Run tool `POST /v1/inventory` ([guide](services/cv/integration_guide_CV.md)) | Michal | req. 13 |
| GCP deployment (later: Terraform / IaC, not console-only) | Michal | — |

Local GCP mock: [`mock-firestore-app/`](mock-firestore-app/). Job API + `fn-prepare` + three services (`cv`, `email` stub, `editor` stub). Files in the bucket, job records in Firestore. No polling worker.

## What it is

An email-driven service that receives forms plus a free-text **manifest**, then hands off to an AI editor that either:

- **Derivative** — validates supplied Word forms against parsed requirements
- **Net-new** — composes a new form from client inputs

Both modes return Word documents with review comments (pass/fail + justification + suggestion, or how each requirement was realised).

## Architecture (v1)

```
client email
  → intake validation (missing docs / missing manifest)
  → confirmation reply (recommended: include parsed requirement list)
  → AI editor (scoped agent runs, shared Python document state)
  → Word output with comments
```

- Manifest is normalised into discrete, checkable requirements before the editor sees it.
- Each agent run is scoped to a **slice** of the manifest, not the whole thing.
- Artifact state lives **outside** any single run (Python object, line-addressable).
- Edits are surgical (line-targeted). No full regeneration.
- Reasoning tools include image processing / understanding / cropping.
- After each run: Pydantic validator (every requirement answered, every answer justified, every reference resolves). Retry up to 3 times, then mark unverified.

## Deferred / open

| ID | Topic | Status |
|----|--------|--------|
| D1 | Input formats beyond Word (PDF/scan → OCR) | Deferred |
| D2 | Job status / failure visibility after confirmation | Deferred |
| D3 | Cross-requirement conflicts (per-slice agents miss them) | Open |
