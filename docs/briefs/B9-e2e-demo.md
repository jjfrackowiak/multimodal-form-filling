# B9 · End-to-end demo

**Branch:** `feat/e2e-demo` → PR into `main`
**Depends on:** everything — B0 through B15, B6 and B7 especially.
**Needs:** no live model. The demo runs on `FakeLlm` + `InMemoryTransport` + in-memory
stores. A live variant behind an env flag is optional.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

A single test script that proves the whole pipeline works end-to-end: an email arrives,
gets parsed, jobs are orchestrated, slices are reviewed, documents are compiled, and a
reply is sent back. All offline, all in-process, all against the fleet fixture.

```
scripts/e2e_demo.py          — the runnable demo / test
services/email-service/tests/e2e/     — pytest-wrapped variant
```

## What it exercises

```
InboundMessage (fixture email)
  → parse_inbound (B3)
  → validate_intake (B3)
  → parse_manifest (B2, via extractor)
  → run_request (B5)
      → per job: sequential slices
          → run_slice (B8) with B6 or B7 flow
  → compile (B1)
  → deliver (B13)
  → send reply (B4 InMemoryTransport)
```

## The email

Build an `InboundMessage` from the fleet fixture:
- Body: `manifest.txt`
- Attachments: `derivative.zip` containing `form_supplied.docx`, `net-new.zip` containing
  `WN-7020U/` folder
- From: an allowed sender
- Subject: anything

This is a **mixed-mode request**: one derivative job and one net-new job.

## The fake runner

Use `FakeSliceRunner` — the orchestrator's test double from B5 — scripted with the golden
review from `expected_output/review.yaml`. The agent flows (B6/B7) are exercised through
`FakeLlm` scripted with the same golden comments.

If the flows are not yet landed when you start, fall back to `FakeSliceRunner` alone and
add a TODO for the flow-level variant.

## The assertion

Run `check_output.py` on the produced document. 156/156 is the bar. Also assert:

1. The reply email was "sent" via `InMemoryTransport`.
2. The reply has the right number of attachments (one reviewed .docx per job).
3. The delivery body contains all 10 requirement ids.
4. The `RequestResult.status` is `"done"` (both jobs complete).

## Directories you own

```
scripts/e2e_demo.py
services/email-service/tests/e2e/
```

## Definition of done

1. `make check` green.
2. `python scripts/e2e_demo.py` exits 0.
3. `check_output.py` passes 156/156 on the produced document.
4. Both derivative and net-new jobs complete in one run.
5. The demo runs in under 10 seconds (no network, no model).
6. No credentials required — runs on `FakeLlm` + `InMemoryTransport` + in-memory stores.

## Out of scope

Live model testing (optional stretch goal), Docker, deployment, GCP.
