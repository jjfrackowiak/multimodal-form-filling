# Shared context — read this before your brief

Every brief assumes this page. It is the 15% of `docs/app-implementation-plan.md`
(1,300 lines) that every branch needs. Read your brief, read this, and consult the plan
only for the section your brief names.

---

## What the system does

A client emails a **manifest** (free text describing what a form must contain) plus zero or
more **Word forms**. The service replies twice: a confirmation listing the requirements it
parsed, then — minutes later — the reviewed documents.

Two modes:

- **Derivative** — forms supplied. Check them against the manifest and attach review
  comments. **The client's document is never modified.**
- **Net-new** — no forms. Compose a document from the manifest and the client's inputs.

Source spec: `multimodal-form-filling/email-form-validation-requirements.pdf`, 17 numbered
requirements. Briefs cite them as "req 5", "req 17".

## What an email looks like

**The manifest is always the email body.** Never an attachment.

```
email body               → the manifest, byte-for-byte
derivative.zip           → each .docx inside     = one DERIVATIVE job
net-new.zip              → each top-level folder = one NET-NEW job
a bare .docx             → one DERIVATIVE job
```

A folder inside the net-new zip is one set of inputs — its `.txt` files and its images. The
folder name becomes `form_id`, so the client's own label survives into the reply.

**Containment is how a client says what belongs to what.** An image in `pojazd-A/` belongs
to the `pojazd-A` job.

**One email may carry both kinds.** Three forms to validate plus four sets to compose is
seven jobs, one request, one delivery email. `mode` therefore lives on `JobRequest` and
**not** on `RequestRecord` — never assume a request is homogeneous.

## The shape

```
Request                     one client email
  └── Job  (one work item)  ← PARALLEL. A .docx to validate, or a folder of
        │                      inputs to compose from. Both may appear together.
        └── Slice           ← SEQUENTIAL: requirements within a job interact
```

A **slice** is at most 6 requirements, taken in manifest order. Slices run in sequence so
slice N sees what slices 1…N−1 committed — that is what makes interdependent requirements
possible at all.

```
email ─▶ email-service ─┬─ intake, replies      (B3)
                        ├─ transport            (B4)
                        ├─ orchestrator/runner  (B5)
                        └─ delivery             (B13)
                              │
                              ├──▶ editor-service   POST /slices:run   (B8 + B6/B7)
                              └──▶ vision-service   POST /v1/inventory (exists, stubbed)
```

**The editor service is the only thing that calls a model.** Everything deterministic —
compiling documents, persistence, completeness, delivery — is on the other side of that
line. That is why `python-docx` must not appear in the editor, and `pydantic-ai` must not
appear in the email service.

## What B0 left you

Merged in `main` as PR #1. `make check` is green; do not break it.

```
pyproject.toml              uv workspace root, shared ruff/mypy/import-linter config
Makefile                    make check = ruff + mypy --strict + import-linter + pytest
.github/workflows/ci.yml    runs the same on every PR, offline, no secrets

packages/
  mff-contracts/    ★ FROZEN — 9 modules, 77 tests, 100% coverage
  mff-vision/         VisionTool Protocol, HTTP client, deterministic stand-in (13 tests)
  mff-docmodel/       empty skeleton  → B1
  mff-manifest/       empty skeleton  → B2
  mff-applier/        empty skeleton  → B14
  mff-store/          empty skeleton  → B12

services/
  email-service/      empty skeleton  → B3, B4, B5, B13
  editor-service/     empty skeleton  → B8, then B6/B7
  vision-stub/        working placeholder service

fixtures/fleet-vehicle-return/    real submission, golden data — see below
scripts/verify_mailbox.py         proves a mailbox works before you debug your code
docker/compose.dev.yaml           GreenMail on SMTP 3025 / IMAP 3143
```

An empty skeleton is a `pyproject.toml`, `src/<pkg>/__init__.py` and `tests/test_smoke.py`.
**Add files to yours; do not restructure it.**

## The contract surface

`mff_contracts` exports 36 types. The ones most branches touch:

| Group | Types |
|---|---|
| Manifest | `Requirement`, `Manifest`, `SlicePlan` |
| Blobs & images | `BlobRef`, `JobImage`, `ImageAnalysis`, `RequirementSpec` |
| Documents | `Node` (derivative) · `Entry`, `Section`, `FormDraft`, `DraftOp` (net-new) |
| Review | `ReviewComment`, `Anchor` |
| Artifacts | `DerivativeArtifact`, `NetNewArtifact`, `Artifact` (union) |
| Slices | `SliceRequest`, `SliceReport` |
| Compile | `RunSpan`, `RenderMap`, `CompiledForm` |
| Lifecycle | `Mode`, `RequestRecord`, `JobRequest`, `RequestAccepted`, `JobRecord`, `JobCursor`, `RequestResult`, `IntakeVerdict`, `IntakeProblem` |
| Repositories | `ArtifactRepository`, `JobRepository`, `RequestRepository`, `BlobStore` |

Read `packages/mff-contracts/src/mff_contracts/` directly — it is 9 short files and the
docstrings explain the design decisions.

**`mff-contracts` is frozen.** No branch edits it. If you need a change, say so in the PR
description and stop; ten branches depend on that shape.

## The fixture is the shared reference

`fixtures/fleet-vehicle-return/` — a real vehicle-return photo submission with a real
client-written Polish manifest. Most briefs assert against it.

```
manifest.txt                        10 lines, real, misspelled — do not normalise it
images/                             17 files, but only 15 distinct (2 byte-identical pairs)
inventory.yaml                      human labels: what each photo shows
expected_requirements.yaml          the golden parse — 10 requirements, R-01…R-10
input/derivative/form_supplied.docx the submitted report, 2.8 MB, 17 embedded photos
input/netnew/client_inputs.yaml     same submission, no document
expected_output/report_reviewed.docx  golden output, 10 real Word comments
expected_output/delivery.txt          the results email
expected_output/structure.yaml        THE EVAL TARGET
check_output.py                       reference evaluator — 156 assertions, offline
```

**The case it exists to catch:** the manifest asks for two headliner photos, and a
constraint **six lines later** says they must be shot from between the front seats. Two
were supplied; one satisfies it, one does not. So R-04 is **superficially met and
substantively failed** — any implementation that counts photos per category passes it and
is wrong.

Run the evaluator any time:

```bash
.venv-fixture/bin/python fixtures/fleet-vehicle-return/check_output.py \
    fixtures/fleet-vehicle-return/expected_output/report_reviewed.docx
→ PASS  156/156 checks passed
```

## Rules every branch inherits

**Own your directories, nothing else.** That table is what makes concurrent PRs safe.

**No live model calls in CI.** `TestModel` / `FunctionModel`. Live evals go behind an env
flag, run manually, baseline recorded in the package README.

**No LLM-as-judge.** `pydantic_evals.evaluators.LLMJudge` is banned by a ruff rule and
fails lint. Every evaluator here is structural — the pipeline is non-deterministic, whether
its output is complete is not.

**Mutation-test your evaluator.** Break your own golden output in at least three ways and
show each caught. Three checkers in this repo have already silently asserted nothing,
including one in the fixture's own suite.

**Report what the spec got wrong.** B0's report caught an `import-linter` rule of mine that
would have blocked every eval suite in the repo. That is worth more than a clean report.

## `services/email-service/pyproject.toml` — the one shared file

B3, B4, B5 and B13 all live in that service and all need to add dependencies to its single
`pyproject.toml`. **Expect a conflict there and keep your edit to one line.** It is the
only file in Layer 1 that more than one branch legitimately touches.

## Definition of done — the hierarchy

`make check` green is the **floor**, not the bar. It means you did not break the workspace.
The numbered assertions in your brief are the actual deliverable — they are specific on
purpose, because "tests pass" is compatible with testing nothing.
