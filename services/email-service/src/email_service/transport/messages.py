"""Message shapes shared by intake, delivery and the transport itself.

These live here — not in `mff-contracts` — because they are internal to the email
service. They are not a wire contract between services; nothing outside this service ever
sees an `InboundMessage`.

They are also **in-process only**: `Attachment.data` is raw `bytes`, which pydantic cannot
serialise to JSON. That is deliberate rather than an oversight — attachments go to the blob
store on ingest, so a message never needs to survive a queue hop carrying its payload. If a
deployment ever needs one to, encode at that boundary rather than making every message pay
for it.

Placed on `main` ahead of B3, B4 and B13 because all three need them and would otherwise
each invent their own. **B4 owns this module** and may extend it; B3 and B13 import from it
and should not change it without saying so.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

__all__ = ["Attachment", "InboundMessage", "OutboundMessage"]


class Attachment(BaseModel):
    """One attached file, already decoded.

    `filename` is the decoded name — MIME may carry it RFC 2047 encoded
    (`=?UTF-8?B?...?=`), and `protocol.docx` arriving as gibberish would fail an
    extension check on a perfectly valid file.
    """

    filename: str
    content_type: str
    data: bytes


class InboundMessage(BaseModel):
    """A message as received. The body IS the manifest — never an attachment."""

    message_id: str  # idempotency key; never rely on \\Seen state
    sender: str
    subject: str
    body: str  # the manifest, byte-for-byte
    attachments: list[Attachment] = Field(default_factory=list)
    received_at: datetime
    headers: dict[str, str] = Field(default_factory=dict)  # Auto-Submitted, List-Id, …


class OutboundMessage(BaseModel):
    """A reply. Threading is against the ORIGINAL client message, never our own."""

    to: str
    subject: str
    body: str
    html_body: str | None = None  # optional multipart/alternative; plaintext stays canonical
    attachments: list[Attachment] = Field(default_factory=list)
    in_reply_to: str | None = None  # the client's Message-ID
    references: list[str] = Field(default_factory=list)
    auto_submitted: bool = True  # so other robots do not reply to us
