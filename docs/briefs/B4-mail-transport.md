# B4 · Mail transport

**Branch:** `feat/mail-transport` → PR into `main`
**Depends on:** B0 (merged).
**Needs:** no API key. GreenMail via Docker for the integration tests; nothing at all for
the unit tests.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`services/email-service/src/**/transport/**` — the only code in the repo that touches a
mail server, behind a Protocol so nothing else has to.

```python
class MailTransport(Protocol):
    async def fetch_unseen(self) -> list[InboundMessage]: ...
    async def mark_seen(self, message_id: str) -> None: ...
    async def send(self, message: OutboundMessage) -> None: ...
```

Three implementations' worth of value in two: **`ImapSmtpTransport`** for real servers and
**`InMemoryTransport`** as the fake every other branch tests against. The fake is not an
afterthought — B3, B5 and B13 all depend on it, so ship it first and make it good.

`InboundMessage` and `OutboundMessage` are yours to define in this package. They are
internal, not wire types, so they do not belong in `mff-contracts`.

## Requirements you own

Reqs 1 and 2 (receiving), and the transport half of 7, 8 and 10 (sending).

## Directories you own

```
services/email-service/src/**/transport/**
services/email-service/tests/transport/**
```

`intake.py` is B3's. `orchestrator/` and `runner/` are B5's. `delivery.py` is B13's.

## Use GreenMail, not Mailpit

An earlier draft of the plan said Mailpit. That was wrong and it is worth knowing why:
**Mailpit is SMTP-only for receiving and speaks no IMAP**, so the inbound poller — the
entire receiving half of this branch — cannot be developed against it. Verified against
Mailpit's own documentation.

`docker/compose.dev.yaml` already runs GreenMail: SMTP 3025, IMAP 3143, TLS variants on
3465/3993, REST API on 8080. Auth is disabled there, so any credentials work and the
mailbox is created on first use.

`scripts/verify_mailbox.py` already exists and passes against real Gmail. Run it before
debugging anything — it separates "our code is wrong" from "the mailbox is not up".

## Things that will bite

**Gmail drops idle IMAP connections, and `IDLE` must be re-issued** before the ~29 minute
limit. **The poller must reconnect rather than assume a durable connection.** A poller that
works for twenty minutes and then quietly stops looks exactly like "no mail arrived", which
is the most expensive failure mode available here.

**Idempotency is keyed on `Message-ID`, not on read state.** Gmail's IMAP folders are
labels and its `\Seen` semantics differ from a conventional server. Keying on Message-ID
means none of that matters.

**`IMAP_FOLDER` is configuration, never an assumption.** Gmail exposes labels as folders,
so a filter routing `you+forms@gmail.com` to a `FormRequests` label lets the poller read
only that label. Default `INBOX`, but never hardcode it.

**Threading.** A reply sets `In-Reply-To` and `References` against the **original client
message**, never against our own confirmation — otherwise request, confirmation and results
do not read as one conversation.

**GCP blocks outbound port 25 permanently, with no exceptions.** 587 and 465 are
unrestricted. Use 587. **Never build a fallback to 25** — it works locally and fails
silently the moment it is deployed, which is the single most common way a working mail
integration dies on that platform.

**Never auto-reply** to a message carrying `Auto-Submitted: auto-*`, a `List-Id`, or a null
return path. That is the rule that stops two robots talking to each other forever.

**Credentials are injected at runtime**, never baked into an image.

## Definition of done

1. `make check` green, coverage ≥ 85%.
2. `InMemoryTransport` passes the **same test suite** as `ImapSmtpTransport`, parametrised.
3. Integration test against GreenMail: send with a `.docx` attachment and Polish text,
   fetch it back, assert both survived. (`verify_mailbox.py` already proves the shape.)
4. Idempotency: the same `Message-ID` delivered twice is processed once.
5. Reconnect: kill the connection mid-poll, assert recovery rather than a silent stop.
6. Threading headers assert against the *original* message id.
7. An auto-submitted message is not replied to.
8. CI runs the in-memory suite with **no Docker**.

## Out of scope

Deciding whether a message is a valid request (B3), what a reply says (B3/B13), job
orchestration (B5). You move bytes; you do not interpret them.
