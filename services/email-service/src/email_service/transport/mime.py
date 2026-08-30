"""Convert between raw MIME (`email.message.Message`) and our internal shapes.

Isolated from `imap_smtp.py` so the parsing/building logic is testable without a
socket — a mailbox round trip is a network concern, decoding RFC 2047 correctly is
not, and the two should not have to fail together.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email import utils as email_utils
from email.header import decode_header, make_header
from email.message import EmailMessage, Message

from .messages import Attachment, InboundMessage, OutboundMessage

__all__ = ["build_outbound_email", "parse_inbound_message"]


def _decode_words(value: str | None) -> str:
    """Undo RFC 2047 encoded-words (`=?UTF-8?B?...?=`).

    Without this, `protokół.docx` — or a Polish subject line — arrives as gibberish.
    `Message.get_filename()` and header accessors hand back the raw encoded-word form;
    nothing decodes it for you.
    """
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def _parse_date(value: str | None) -> datetime:
    if value:
        try:
            parsed = email_utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None:
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    # Missing or unparseable Date header: better a timestamp than a crash.
    return datetime.now(UTC)


def parse_inbound_message(raw: Message) -> InboundMessage:
    """Build an `InboundMessage` from a message as IMAP hands it back.

    `headers` keeps the first occurrence of each header name — good enough for the
    loop-guard / threading headers this exists to serve, which never repeat.
    """
    headers: dict[str, str] = {}
    for key, value in raw.items():
        headers.setdefault(key, str(value))

    body = ""
    attachments: list[Attachment] = []
    for part in raw.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        if filename:
            payload = part.get_payload(decode=True)
            attachments.append(
                Attachment(
                    filename=_decode_words(filename),
                    content_type=part.get_content_type(),
                    data=payload if isinstance(payload, bytes) else b"",
                )
            )
        elif part.get_content_type() == "text/plain" and not body:
            payload = part.get_payload(decode=True)
            raw_body = payload if isinstance(payload, bytes) else b""
            body = raw_body.decode(part.get_content_charset() or "utf-8", "replace")

    return InboundMessage(
        message_id=(raw.get("Message-ID") or "").strip(),
        sender=_decode_words(raw.get("From")),
        subject=_decode_words(raw.get("Subject")),
        body=body,
        attachments=attachments,
        received_at=_parse_date(raw.get("Date")),
        headers=headers,
    )


def build_outbound_email(message: OutboundMessage, *, mail_from: str) -> EmailMessage:
    """Build the wire message for `OutboundMessage`.

    Threading headers (`In-Reply-To` / `References`) are copied verbatim from the
    message we are given — this function does not choose them. Getting them to point
    at the client's original message, never our own confirmation, is the caller's
    responsibility (see `OutboundMessage.in_reply_to`'s docstring).
    """
    email_msg = EmailMessage()
    email_msg["From"] = mail_from
    email_msg["To"] = message.to
    email_msg["Subject"] = message.subject
    email_msg["Message-ID"] = email_utils.make_msgid()
    if message.in_reply_to:
        email_msg["In-Reply-To"] = message.in_reply_to
    if message.references:
        email_msg["References"] = " ".join(message.references)
    if message.auto_submitted:
        # RFC 3834 — this is the header the loop guard on the *receiving* end checks.
        email_msg["Auto-Submitted"] = "auto-replied"
    email_msg.set_content(message.body)
    if message.html_body:
        email_msg.add_alternative(message.html_body, subtype="html")
    for attachment in message.attachments:
        maintype, _, subtype = attachment.content_type.partition("/")
        email_msg.add_attachment(
            attachment.data,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=attachment.filename,
        )
    return email_msg
