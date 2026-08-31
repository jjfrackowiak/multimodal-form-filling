# Multimodal Form Filling

Email-driven form validation / composition. Spec: [`multimodal-form-filling/email-form-validation-requirements.pdf`](multimodal-form-filling/email-form-validation-requirements.pdf) (30 August 2026).

## Ownership

| Area | Owner | Spec |
|------|--------|------|
| Email service (intake, confirmation / rejection replies, handoff) | Janek | Part 1 |
| AI editor (scoped agent runs, document state, line edits, Pydantic retry) | Janek | Part 2 |
| Image / CV — Cloud Run tool `POST /v1/inventory` ([guide](services/cv/integration_guide_CV.md)) | Michal | req. 13 |
| GCP deployment (later: Terraform / IaC, not console-only) | Michal | — |

## What it is

An email-driven service that receives forms plus a free-text **manifest**, then hands off to an AI editor that either:

- **Derivative** — validates supplied Word forms against parsed requirements
- **Net-new** — composes a new form from client inputs

Both modes return Word documents with review comments (pass/fail + justification + suggestion, or how each requirement was realised).

Ready-to-send inputs for both modes — no setup, just paste and attach — are in
[`demo-examples/`](demo-examples/).

## Deployed architecture

![Amendo architecture: Gmail, three Cloud Run services (email-service, editor-service, cv), Firestore, Cloud Storage, Vertex AI (Gemini 3.5 Flash + Gemma, plus cv's own model), and the GitHub Actions → WIF → Cloud Build → Artifact Registry → Terraform deploy path](docs/architecture.svg)

`email-service` polls the mailbox over IMAP, drives every request through Firestore/Cloud Storage, and is the only thing a client ever talks to. `editor-service` is the only piece allowed to call a model directly in the request path — everything else on the diagram is deterministic. A third service, `cv`, is independently owned and does its own model call for photo-to-requirement matching; in this deployment `editor-service` bypasses it in favour of a bundled fixture inventory (see `docs/architecture.md`). All three are Cloud Run services in the same GCP project and region, deployed by Terraform through a keyless GitHub Actions pipeline.

Full write-up — both models, every Terraform file, the CI/CD tiers, and the gaps we didn't paper over — in [`docs/architecture.md`](docs/architecture.md).

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

## Reproducible testing

Everything below is deterministic, offline, and needs no API key, GCP project, or
mailbox — no live model calls, no network. Run from the repo root.

```bash
uv sync --all-packages   # install once
make check                # ruff + mypy --strict + import-linter + the full pytest suite
```

**One command that exercises the whole pipeline**, end to end, against a real
client submission — parses a manifest, runs both a derivative and a net-new job
through a fake (but contract-accurate) LLM, compiles both documents, attaches
review comments, and grades the output structurally:

```bash
uv run python scripts/e2e_demo.py
```

Expected tail of the output:

```
B9 e2e demo: PASS
RequestResult status: done
jobs done: 2; attachments: 3
PASS  156/156 checks passed
```

That last line is the fixture's own reference evaluator
([`fixtures/fleet-vehicle-return/check_output.py`](fixtures/fleet-vehicle-return/check_output.py)),
runnable on its own against the frozen golden document:

```bash
uv run python fixtures/fleet-vehicle-return/check_output.py \
    fixtures/fleet-vehicle-return/expected_output/report_reviewed.docx
```

156 structural assertions — document shape, review-comment content, inline
anchoring, delivery-email provenance — mutation-tested by deliberately breaking
the golden output five different ways and confirming each is caught (see the
fixture's own [`README.md`](fixtures/fleet-vehicle-return/README.md)).

Live-model evals (the same pipeline against real Gemini, or a real Gmail inbox
end to end) are intentionally separate and manual — see
[`docs/briefs/CONTEXT.md`](docs/briefs/CONTEXT.md) — so nothing above needs a
credential to reproduce.
