"""The fake every other branch tests against.

Not an afterthought — B3, B5 and B13 all depend on it. It satisfies `MailTransport`
with no socket, no Docker and no event loop trickery, and it passes the exact same
parametrised suite `ImapSmtpTransport` does (`tests/transport/test_protocol_suite.py`),
so a test written against it exercises real transport semantics, not a simplification
of them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from .messages import InboundMessage, OutboundMessage

__all__ = ["InMemoryTransport"]


class InMemoryTransport:
    """`deliver()` is the test seam: it puts a message in the simulated mailbox
    exactly as a real one would arrive, so a test can set up a scenario without
    touching a server.

    `sent` is a plain list of everything passed to `send()` — reach for it directly
    when a test only needs to assert on what was sent. When `own_address` is set and
    a sent message's `to` matches it, the send is *also* echoed back into the inbox as
    a new `InboundMessage` — mirroring what a real IMAP fetch would show after sending
    to yourself, which is what lets the shared parametrised suite assert a send +
    fetch round trip identically against both transports.

    Idempotency mirrors `ImapSmtpTransport`: `fetch_unseen()` excludes anything already
    `mark_seen()`-ed, keyed on `message_id` — never on a read flag, because the real
    transport cannot rely on one either (Gmail's `\\Seen` semantics differ).
    """

    def __init__(self, *, own_address: str | None = None) -> None:
        self._own_address = own_address
        self._inbox: list[InboundMessage] = []
        self._seen_ids: set[str] = set()
        self.sent: list[OutboundMessage] = []

    def deliver(self, message: InboundMessage) -> None:
        self._inbox.append(message)

    async def fetch_unseen(self) -> list[InboundMessage]:
        found: dict[str, InboundMessage] = {}
        for message in self._inbox:
            if message.message_id in self._seen_ids:
                continue
            found.setdefault(message.message_id, message)
        return list(found.values())

    async def mark_seen(self, message_id: str) -> None:
        self._seen_ids.add(message_id)

    async def send(self, message: OutboundMessage) -> None:
        self.sent.append(message)
        if self._own_address is not None and message.to == self._own_address:
            self._inbox.append(_echo_as_inbound(message, sender=self._own_address))


def _echo_as_inbound(message: OutboundMessage, *, sender: str) -> InboundMessage:
    headers: dict[str, str] = {}
    if message.in_reply_to:
        headers["In-Reply-To"] = message.in_reply_to
    if message.references:
        headers["References"] = " ".join(message.references)
    if message.auto_submitted:
        headers["Auto-Submitted"] = "auto-replied"
    return InboundMessage(
        message_id=f"<{uuid.uuid4().hex}@in-memory.test>",
        sender=sender,
        subject=message.subject,
        body=message.body,
        attachments=list(message.attachments),
        received_at=datetime.now(UTC),
        headers=headers,
    )
