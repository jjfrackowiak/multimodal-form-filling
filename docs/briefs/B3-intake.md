# B3 · Intake and replies

**Branch:** `feat/intake` → PR into `main`
**Depends on:** B0 (merged). B4's `MailTransport` Protocol and `InMemoryTransport` — if B4
has not landed, define the Protocol you need and expect a small merge.
**Needs:** nothing. No key, no mailbox, no Docker.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`services/email-service/src/**/{intake,replies}.py` — turning an inbound message into
either a rejection or a job, and writing both replies.

```python
def parse_inbound(msg: InboundMessage) -> ParsedRequest: ...
def validate_intake(req: ParsedRequest) -> IntakeVerdict: ...
def render_rejection(verdict: IntakeVerdict, req: ParsedRequest) -> OutboundMessage: ...
def render_confirmation(accepted: RequestAccepted, req: ParsedRequest) -> OutboundMessage: ...
```

## Requirements you own

**Reqs 6, 7 and 8**, and req 3 (validation requests must supply the initial forms).

## Directories you own

```
services/email-service/src/**/intake.py
services/email-service/src/**/replies.py
services/email-service/tests/intake/**
```

## You must never parse the manifest

This is the constraint that matters most on this branch.

Req 7 says the confirmation reply carries the parsed requirement list. It is tempting to
parse the manifest here to produce it. **Do not.** The parser has a model in it and is
therefore non-deterministic: two parses of the same manifest can differ, and the client
would be shown one list while their document was graded against another — silently
destroying the exact thing req 7 exists to provide.

The editor parses **once** and returns `RequestAccepted.requirements` in the 202.
`render_confirmation` **quotes that**. Nothing in this branch imports a model library, and
`import-linter` enforces it.

## Reading an email — the shape you must implement

**The manifest is always the email body.** Never an attachment. That is fixed, and it
removes a whole class of question: which attachment is the manifest, what format, what if
there are two. `RequestRecord.manifest_raw` is the body text byte-for-byte, because
`Requirement.source_span` quotes from it.

**Attachments are work items:**

```
derivative.zip           → each .docx inside      = one DERIVATIVE job
net-new.zip / netnew.zip → each top-level folder  = one NET-NEW job
a bare .docx attachment  → one DERIVATIVE job
```

Inside the net-new zip, **one folder is one set of inputs** — its `.txt` files and its
images:

```
net-new.zip
├── pojazd-A/          → job, form_id "pojazd-A"
│   ├── dane.txt       → ClientInputs.texts["dane.txt"]
│   └── *.jpg          → JobRequest.images
└── pojazd-B/          → another job
```

**The folder name becomes `form_id`**, so the client's own labelling survives into the
results email. They named it; refer to it by that name.

**Containment is how a client says what belongs to what.** An image in `pojazd-A/` belongs
to the `pojazd-A` job. No naming convention to learn, no metadata file. This is the answer
to a question that was open for a long time — do not reinvent a different one.

## One email can carry both modes

The realistic complex case: `derivative.zip` with three forms **and** `net-new.zip` with
four input sets = **seven jobs, one request, one delivery email.**

`mode` lives on `JobRequest`, **not** on `RequestRecord`. Do not infer a single mode for
the email — that was the old shape and it could not express this. Build a list of work
items, each with its own mode, and a model validator enforces that derivative carries a
`form` and net-new carries `inputs`.

## Unzipping is attacker-facing

These archives come from outside. Before extracting anything:

- **Reject path traversal.** An entry named `../../etc/passwd` must not escape the
  extraction root. This is zip-slip and it is the classic one.
- **Reject absolute paths and symlinks.**
- **Cap entry count and total uncompressed size**, checked *before* extraction. A zip bomb
  is a plausible accident as much as an attack — someone zips a folder of RAW photos.
- **Extract to a temp directory you control**, never in place.

Use `zipfile` and validate every `ZipInfo.filename` yourself. `extractall` is not safe on
untrusted input.

## The intake rule matrix (req 6, req 8)

Every rejection must say **exactly what to add or change**. `IntakeProblem(code, detail)` —
`code` for us, `detail` for a human. At minimum:

| Situation | Code |
|---|---|
| No manifest at all | `missing_manifest` |
| Manifest present but empty | `empty_manifest` |
| No work items at all — no zip, no `.docx` | `no_work_items` |
| An attachment that is not a `.docx` or a recognised zip | `unsupported_format` (D1: v1 is Word only) |
| A zip with no usable work items inside | `empty_archive` |
| A net-new zip whose entries are loose files, not folders | `unstructured_inputs` |
| Path traversal, absolute path or symlink in a zip | `unsafe_archive` |
| Archive exceeds the entry or size cap | `archive_too_large` |
| Sender not in `ALLOWED_SENDERS` | `sender_not_allowed` |
| Rate cap exceeded | `rate_limited` |

`ALLOWED_SENDERS` empty means *anyone* gets a reply, which makes the service an open robot
that answers spam and can bounce-loop with another autoresponder. Default to closed.

## Real client MIME is messier than anything you will write

Every message in our fixtures is one we generated, so it is exactly as well-formed as our
own assumptions. Real requests arrive forwarded through three people, with inline images
that should have been attachments, `Content-Disposition` headers disagreeing with the
filename, and Polish text in whatever encoding the sender's client chose. Be liberal in
what you accept and explicit about what you reject.

**Attachment filenames may be RFC 2047 encoded** (`=?UTF-8?B?...?=`). Decode them, or
`protokół.docx` arrives as gibberish and your `.docx` check fails on a valid file.

## What to test against

Build your test emails from `fixtures/fleet-vehicle-return/`:

- **`manifest.txt`** is the **email body**. Not an attachment.
- **`input/derivative/form_supplied.docx`** zipped as `derivative.zip` → one derivative job.
- **`input/netnew/WN-7020U/`** zipped as `net-new.zip` → one net-new job, `form_id`
  `WN-7020U`, its two `.txt` files becoming `ClientInputs.texts` and its 17 images becoming
  `JobRequest.images`.
- Both zips in one email → the mixed case.

## Definition of done

1. `make check` green, coverage ≥ 85%.
2. **Every row of the rule matrix has a test**, asserting the `code` and that `detail`
   names the fix.
3. A test that this package imports no model library — `pydantic-ai` must not appear.
4. `render_confirmation` output contains every requirement id and text from the
   `RequestAccepted` it was handed, and the fixture's ten requirements round-trip.
5. **The seven-job case**: an email with a 3-form `derivative.zip` and a 4-set
   `net-new.zip` produces 7 `JobRequest`s — 3 derivative with `form` set, 4 net-new with
   `inputs` set — and `form_id` matches the `.docx` filenames and folder names.
6. A zip-slip archive (`../escape.docx`) is rejected with `unsafe_archive` and **nothing is
   written outside the temp root** — assert on the filesystem, not just the verdict.
7. A zip declaring a huge uncompressed size is rejected **before** extraction.
6. An RFC 2047 encoded Polish filename is decoded correctly.
7. A `.docx` with the wrong extension and a `.pdf` with a `.docx` name both land the right
   verdict — sniff content, do not trust the name.

## Out of scope

Parsing the manifest (editor), sending anything (B4), the results email (B13), job
lifecycle (B5).
