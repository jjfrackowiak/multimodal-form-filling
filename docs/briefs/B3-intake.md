# B3 · Intake and replies

**Branch:** `feat/intake` → PR into `main`
**Depends on:** B0 (merged). B4's `MailTransport` Protocol and `InMemoryTransport` — if B4
has not landed, define the Protocol you need and expect a small merge.
**Needs:** nothing. No key, no mailbox, no Docker.

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

## Mode inference

Req 3: a validation request must supply the initial version of each form. So forms present
→ `DERIVATIVE`; no forms → `NET_NEW`. Be explicit about the ambiguous case — forms present
*and* the client asking for something new — and put your resolution in the code as a named
rule with a comment, not an inline `if`.

## The intake rule matrix (req 6, req 8)

Every rejection must say **exactly what to add or change**. `IntakeProblem(code, detail)` —
`code` for us, `detail` for a human. At minimum:

| Situation | Code |
|---|---|
| No manifest at all | `missing_manifest` |
| Manifest present but empty | `empty_manifest` |
| Derivative mode with no forms attached | `missing_forms` |
| An attachment that is not a `.docx` | `unsupported_format` (D1: v1 is Word only) |
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

## Definition of done

1. `make check` green, coverage ≥ 85%.
2. **Every row of the rule matrix has a test**, asserting the `code` and that `detail`
   names the fix.
3. A test that this package imports no model library — `pydantic-ai` must not appear.
4. `render_confirmation` output contains every requirement id and text from the
   `RequestAccepted` it was handed, and the fixture's ten requirements round-trip.
5. Mode inference tested both ways plus the ambiguous case.
6. An RFC 2047 encoded Polish filename is decoded correctly.
7. A `.docx` with the wrong extension and a `.pdf` with a `.docx` name both land the right
   verdict — sniff content, do not trust the name.

## Out of scope

Parsing the manifest (editor), sending anything (B4), the results email (B13), job
lifecycle (B5).
