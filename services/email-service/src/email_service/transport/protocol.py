"""`MailTransport` — the seam that keeps a real mail server out of every other branch's
tests. `ImapSmtpTransport` (this package) satisfies it for real; `InMemoryTransport`
(this package) satisfies it for everyone else — B3, B5 and B13 test against the fake,
never against a socket.
"""

from __future__ import annotations

from typing import Protocol

from .messages import InboundMessage, OutboundMessage

__all__ = ["MailTransport"]


class MailTransport(Protocol):
    """Move bytes; do not interpret them.

    `fetch_unseen` returns messages not yet processed — keyed on `Message-ID`, never
    on a server-side read flag (Gmail's `\\Seen` semantics do not mean what a
    conventional server means by it, and its folders are labels, not a partition).

    `mark_seen` records a `Message-ID` as processed so a later `fetch_unseen` excludes
    it. It is a promise about *our* bookkeeping, not necessarily a flag on the server.

    `send` transmits exactly the `OutboundMessage` it is given — threading headers,
    auto-submitted marker and all. Deciding what a reply should say, and whether one
    should be sent at all, is the caller's job.
    """

    async def fetch_unseen(self) -> list[InboundMessage]: ...

    async def mark_seen(self, message_id: str) -> None: ...

    async def send(self, message: OutboundMessage) -> None: ...
