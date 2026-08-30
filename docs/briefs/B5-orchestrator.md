# B5 · Orchestrator and runner

**Branch:** `feat/orchestrator` → PR into `main`
**Depends on:** B0 (merged). Ideally B12 and B14; if they have not landed, work against the
Protocols and a stub applier and expect a small merge.
**Needs:** nothing. It is designed to be testable with no editor service, no mailbox and no
credentials.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`services/email-service/src/**/{orchestrator,runner}/**` — the thing that owns a job's
life. Fan a request out into one job per form, walk each job's slices in order, persist
after each, check completeness, compile, and hold the delivery barrier.

```
Request                     one client email — the body is the manifest
  └── Job  (one work item)  ← PARALLEL. A .docx to validate, or a folder of inputs
        │                      to compose from. ONE EMAIL MAY CARRY BOTH KINDS.
        └── Slice           ← SEQUENTIAL: requirements within a job interact
```

**`mode` is per job, not per request.** A single request may hold 3 derivative jobs and 4
net-new ones. Dispatch each according to its own `JobRequest.mode`; never assume a request
is homogeneous.

## Requirements you own

Req 11 (programmatic hand-off, scoped runs), req 12 (state outside any run), and the
sequencing half of 16–17.

## Directories you own

```
services/email-service/src/**/orchestrator/**
services/email-service/src/**/runner/**
services/email-service/tests/orchestrator/**
```

`intake.py`/`replies.py` are B3's, `transport/` is B4's, `delivery.py` is B13's.

## What you do NOT do — read this twice

**Retry and per-requirement validation are not here.** The editor service owns them and
returns a `SliceReport` that is **always well-formed** — complete, or complete-with-
`unverified`. That is why `SliceRequest` has no `pending`, no `history` and no
`validator_error`: retry state never crosses the wire.

If you find yourself writing a retry loop around `SliceRunner`, stop — you are rebuilding
something that was deliberately moved.

## Slice planning is arithmetic

`Manifest.slices()` already exists in `mff-contracts`: sort by `ordinal`, take consecutive
chunks of at most six. **No grouping, no clustering, no strategy.** Any grouping is a guess
about which requirements belong together, and a wrong guess costs a whole slice run to
discover. The fixture's ten requirements give exactly two slices, 6 and 4.

## Sequential slices, parallel jobs

Slices run **in order** so that slice N reads the artifact as slices 1…N−1 committed it.
That is what makes interdependent requirements representable at all — a summary citing
sections above it, a total depending on entries added elsewhere. Under a parallel design
every run would see the same seed and none could see another's work.

Jobs run **concurrently** because interdependence never crosses forms. Bound the
concurrency with a semaphore.

## Commit and advance are one transaction

`ArtifactRepository.save(artifact, cursor, expected_version)` takes both. As two writes, a
crash between them replays a slice (duplicate comments) or skips one (silently missing
requirements). Both are silent, which is why this is a contract shape rather than a
convention.

**A crashed job resumes from its cursor rather than failing.** `failed` is for the
unrecoverable. If `partial` becomes routine, that is a signal about the runner.

## The two checks you do own

1. **Completeness, after the last slice:** every requirement in the manifest carries at
   least one comment, across *all* slices. This is inherently cross-slice — no single run
   knows what the others answered — which is exactly why it cannot live in the editor.
2. **Renderability, at compile:** every comment anchors to something that still exists.

Neither is a second copy of req 16's rules. They are questions no slice run can answer.

## The delivery barrier

One email per request, when **every** job has settled. `status="partial"` means some forms
were reviewed completely and others not at all — **never** a half-reviewed document. That
is structural: compile runs only after the last slice, so a job that dies mid-slice leaves
comments in the store and nothing rendered.

A `done` job containing `unverified` comments is **not** partial. Do not conflate them.

## `SliceRunner` is a Protocol

```python
class SliceRunner(Protocol):
    async def run(self, request: SliceRequest) -> SliceReport: ...
```

Dispatch through it so the whole orchestrator tests end-to-end with a fake runner, no
editor service, no HTTP, no model. That fake is also what B9's e2e test will use.

## What to test against

`fixtures/fleet-vehicle-return/` supplies a whole job without inventing data:

- **`manifest.txt`** + **`expected_requirements.yaml`** → ten requirements that chunk into
  exactly **two slices, 6 and 4**.
- **`input/derivative/form_supplied.docx`** → a derivative job.
- **`input/netnew/WN-7020U/`** → a net-new job, so a **mixed request** is one of each,
  which is the case the contract change exists for.
- **`expected_output/review.yaml`** → what a fake `SliceRunner` should return.

## Definition of done

1. `make check` green, coverage ≥ 85%.
2. **Full job walked end-to-end with a fake runner** on the fleet fixture: 2 slices,
   10 requirements, correct commit order.
3. Resume test: kill after slice 1, restart, assert slice 2 runs and slice 1 does not.
4. Atomicity test: crash between artifact and cursor write leaves neither.
5. Parallel jobs: **a mixed request of 3 derivative + 4 net-new**, assert concurrency is
   bounded, each gets its own artifact, and the derivative ones produce
   `DerivativeArtifact` while the net-new ones produce `NetNewArtifact`.
6. Barrier: 2 done + 1 failed → `RequestResult.status == "partial"`, `failed_forms` names
   the third, documents has 2 entries.
7. A test that no retry loop exists here — a runner returning a report with `unverified`
   is accepted as-is, not re-dispatched.
8. Completeness check catches a dropped slice.

## Out of scope

Retry, per-requirement validation, prompts, agents, the actual editor call over HTTP
(B8 wires that), the results email (B13), rendering (B1).
