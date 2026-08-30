# B13 · Delivery

**Branch:** `feat/delivery` → PR into `main`
**Depends on:** B0 (merged). B4's transport Protocol and fake.
**Needs:** nothing. Develops entirely against the in-memory transport.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`services/email-service/src/**/delivery.py` — **the email service's second role**, and the
one an earlier draft of the plan forgot entirely. Intake was covered; nothing delivered the
finished documents, so the planned system produced nothing a client could see.

```python
async def deliver(result: RequestResult, request: RequestRecord) -> OutboundMessage: ...
```

## Requirements you own

**Req 10** — output returned as Word documents carrying review comments. And most of
concern **D2**, since the client now learns of both completion and failure.

## Directories you own

```
services/email-service/src/**/delivery.py
services/email-service/tests/delivery/**
```

## The two roles share only the transport

| | Role 1 — intake (B3) | Role 2 — delivery (you) |
|---|---|---|
| Trigger | an inbound message | a request whose jobs have all settled |
| Timing | synchronous | minutes later |
| Idempotency key | `Message-ID` | `request_id` |

Different failure modes, different keys. That is why this is its own branch rather than
more surface on intake.

## Triggering

The runner calls back on completion, **and** you sweep for requests in flight too long.
Callback alone loses requests whenever the service restarts; polling alone taxes every
request with latency. The sweep is cheap because `RequestRepository` already exists.

## What the email must carry, beyond attachments

- **A pass/fail summary**, so the outcome is readable without opening anything.
- **Every `unverified` requirement, named explicitly.** This is where req 17 becomes
  visible to a human: the system tried three times and gave up, and the client must be told
  which checks were never completed rather than left to infer it from a document that looks
  complete.
- **`failed_forms`**, when `status == "partial"`. Use the client's own `form_id` — the
  `.docx` filename or the input folder name they chose — not an internal id.
- A request may mix modes, so the email may report on both validated forms and composed
  ones. Group them so a reader can tell which is which.
- **The parsed requirement list.** Comments cite `R-04` and nothing more, so the list is
  where `R-04` is explained — each requirement's text plus the manifest span and line it
  came from. `fixtures/fleet-vehicle-return/expected_output/delivery.txt` is the golden
  example; match its shape.

Putting the list here as well as in the confirmation is not redundant: the confirmation may
be days old, deleted, or read by somebody else, and the documents are useless without the
numbering they reference.

## Attachment size is a constraint, not a detail

The fixture's **single** reviewed document is 2.8 MB with 17 embedded photos. A three-form
request clears Gmail's 25 MB ceiling easily, and many corporate servers cap at 10.

Attach below a configured threshold; above it, `BlobStore.signed_url` and send a link. The
documents already live in GCS, so the link costs nothing.

## Threading and idempotency

`In-Reply-To`/`References` against the **original client message** — `RequestRecord`
carries `original_message_id` for exactly this. Not against our own confirmation.

Idempotent on `request_id`: a callback firing twice, or a callback plus the sweep catching
the same request, must not send two copies. Record delivery on the record **before**
acknowledging the send.

Set `Auto-Submitted: auto-generated` so other robots do not reply to us.

## Definition of done

1. `make check` green, coverage ≥ 85%.
2. Golden test against `expected_output/delivery.txt`: every requirement id listed, every
   quoted span verbatim in `manifest.txt`, the summary counts correct, both failing
   requirements named.
3. Size threshold: a small result attaches, an oversized one links, and the boundary is
   tested from both sides.
4. Idempotency: two callbacks for one `request_id` produce one send.
5. `status="partial"` names `failed_forms` and attaches only the successful documents.
6. A result with `unverified` requirements names every one of them in the body.
7. Threading asserts against the original message id, not the confirmation's.
8. All of the above with `InMemoryTransport` — **no mailbox required**.

## Out of scope

Deciding when a request is complete (B5), sending bytes (B4), rendering (B1), what a
comment says (B6/B7).
