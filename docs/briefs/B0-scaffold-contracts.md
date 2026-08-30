# B0 · Scaffold and frozen contracts

**Branch:** `feat/scaffold-contracts` → PR into `main`
**Blocks:** every other branch. Nothing in Layer 1 can start until this merges.
**Needs:** no API key, no GCP account, no mailbox. Everything here runs offline.

---

## What you are building

The workspace and the frozen contract package that all ten Layer-1 branches build
against. No application logic, no agents, no HTTP handlers — those are other people's
branches and you must not write them.

Read `docs/app-implementation-plan.md` first. Its **"The contract to freeze first"**
section is the specification for this work; the models there are not a sketch.

---

## Requirements you own

None of the spec's 17 directly. You own the *shape* every other branch expresses them in,
which is why getting this wrong is expensive: a mistake here is rework across ten
branches, not one.

---

## Directories you own

```
pyproject.toml                    uv workspace root
Makefile
.github/workflows/ci.yml
packages/mff-contracts/**         ← the real deliverable
```

You may create **empty** package and service skeletons so later branches only add files:

```
packages/mff-docmodel/     packages/mff-manifest/     packages/mff-applier/
packages/mff-store/        services/email-service/    services/editor-service/
```

Each gets a `pyproject.toml`, a `src/<pkg>/__init__.py`, and a `tests/` directory. **Do
not put logic in them.**

Already on `main` and **not yours to touch**: `packages/mff-vision`,
`services/vision-stub`, `fixtures/`, `scripts/`, `docker/`, `docs/`.

---

## The contract

Transcribe the models from the plan's contract section exactly. They are grouped as:

1. **Manifest and requirements** — `Requirement`, `Manifest`
2. **Blobs and images** — `BlobRef`, `ImageAnalysis`, `JobImage`
3. **Document models** — `Node`; `Entry`, `Section`, `FormDraft`, `DraftOp`
4. **Review** — `Anchor`, `ReviewComment`
5. **Artifacts** — `DerivativeArtifact`, `NetNewArtifact`, `Artifact` union
6. **Slices** — `SlicePlan`, `SliceRequest`, `SliceReport`
7. **Compile** — `RunSpan`, `RenderMap`, `CompiledForm`
8. **Job lifecycle** — `Mode`, `IntakeProblem`, `IntakeVerdict`, `RequestRecord`,
   `JobRequest`, `RequestAccepted`, `JobCursor`, `JobRecord`, `RequestResult`
9. **Repositories** — `ArtifactRepository`, `JobRepository`, `RequestRepository`,
   `BlobStore` (Protocols only — no implementations)

### Non-negotiable

**`mff-contracts` depends on pydantic and nothing else.** Not `pydantic-ai`, not
`python-docx`, not `httpx`, not `mff-vision`. Two specific traps, both of which were
caught in review and will be caught again by CI:

- `ImageAnalysis` **lives here**, not in `mff-vision`. `mff-vision` imports it from you.
  Owning it there would make the frozen package depend on a service client.
- `SliceRequest.history` and `SliceReport.history` are **`list[dict[str, Any]]`**, not
  `list[ModelMessage]`. Typing them would drag the whole agent framework into the package
  everything else depends on.

---

## Validators to write

These are the contract's teeth. Each needs a passing and a failing test:

| Rule | Why |
|---|---|
| `suggestion` is required **iff** `verdict == "fail"` | req 10; a failure with no remedy is useless, a pass with one is noise |
| `Anchor.target_id` is set unless `kind == "document"` | an unanchored comment cannot exist in OOXML |
| `justification` is non-empty on every comment | req 16 |
| `DraftOp` field combinations are valid per `kind` | `append` needs `section_id`, `set`/`delete` need `entry_id` |
| `BoundingBox` coordinates are within 0..1 | normalised so crops survive resizing |
| `schema_version` is present on both artifacts | these persist and the shape has already changed twice |

Also provide `Manifest.slices()` returning `list[SlicePlan]`, with:

- `slice.ordinal = min(r.ordinal for r in slice)`, sorted ascending
- **2–6 requirements per slice** — split oversized scopes by `ordinal`, merge undersized
  adjacent ones. Without the bound, slice granularity becomes an accident of how the
  parser happened to phrase `scope`.

---

## Tooling

- **uv workspace**, Python ≥ 3.11.
- **ruff** lint + format, one shared config, no per-package overrides.
- **mypy `--strict`** across the workspace. A `type: ignore` needs an error code and a
  reason.
- **import-linter**, and this is the highest-value gate in the repo. Contracts:
  1. `services → packages → mff-contracts`. Never sideways, never upward.
  2. `mff-contracts` imports nothing but `pydantic`.
  3. No module outside `llm/` and `agents/` imports a model library.
  4. **`pydantic_evals.evaluators.LLMJudge` is forbidden anywhere.** Every evaluator in
     this repo is structural.
- **pytest**, `asyncio_mode = auto` (already set in `pytest.ini`).
- Per-package coverage ≥ 85%, measured per package — a global number lets one
  well-tested package hide four untested ones.

`make check` runs all of it and must pass offline with no credentials.

---

## Wire in what already exists

`packages/mff-vision` and `services/vision-stub` are on `main` and currently install
standalone. Bring them into the workspace, and **move `ImageAnalysis` into
`mff-contracts`**, updating `mff-vision` to import it. Their 13 tests must still pass.

The fixture's evaluator must also still pass:

```
.venv-fixture/bin/python fixtures/fleet-vehicle-return/check_output.py \
    fixtures/fleet-vehicle-return/expected_output/report_reviewed.docx
→ PASS  156/156 checks passed
```

---

## Definition of done

1. `make check` green: ruff, mypy --strict, import-linter, pytest — offline, no keys.
2. Every validator above has a passing **and** a failing test.
3. `Manifest.slices()` tested against the fleet fixture's 10 requirements: ordinals match
   `expected_ordinals` in `expected_output/structure.yaml`, and every slice is 2–6 wide.
4. The existing 13 vision tests pass with `ImageAnalysis` imported from contracts.
5. `check_output.py` still returns 156/156.
6. An import-linter test that **fails** if someone adds `pydantic-ai` to
   `mff-contracts` — prove the gate works rather than assuming it.

## Out of scope — do not write these

Manifest parsing, the docmodel, the applier, the store adapters, the orchestrator, the
runner, agents, prompts, HTTP handlers, Dockerfiles. Those are B1–B14. If the contract
seems to need a change, **say so in the PR description rather than changing it** — ten
branches are about to depend on this shape.
