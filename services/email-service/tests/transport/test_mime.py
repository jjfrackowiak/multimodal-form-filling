"""parse_inbound_message / build_outbound_email — pure MIME conversion, no socket.

This is where DoD-3 (Polish text and a .docx attachment survive) and DoD-6 (threading
headers point at the original message) are provable with no Docker: the round trip
these functions perform is exactly what a real IMAP fetch / SMTP send does to the
bytes, so a bug here fails identically online or off.
"""

from __future__ import annotations

import email

from email_service.transport.messages import Attachment, OutboundMessage
from email_service.transport.mime import build_outbound_email, parse_inbound_message

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_polish_body_survives_the_round_trip() -> None:
    # A trailing "\n" here, not because it is required elsewhere, but because MIME
    # text parts are always newline-terminated on the wire — `set_content` adds one
    # if it is missing, so a body already ending in one is what round-trips exactly.
    body = "16 zdjęć,\nPod maską\n4x fotele i 2 przekątne pojazdu\n"
    outbound = OutboundMessage(to="klient@example.test", subject="Wynik walidacji", body=body)
    wire = build_outbound_email(outbound, mail_from="svc@example.test")
    reparsed = email.message_from_bytes(wire.as_bytes())

    inbound = parse_inbound_message(reparsed)
    assert inbound.body == outbound.body


def test_attachment_survives_the_round_trip() -> None:
    outbound = OutboundMessage(
        to="klient@example.test",
        subject="Recenzja",
        body="w załączniku",
        attachments=[
            Attachment(filename="protokół.docx", content_type=DOCX, data=b"PK\x03\x04zawartosc")
        ],
    )
    wire = build_outbound_email(outbound, mail_from="svc@example.test")
    reparsed = email.message_from_bytes(wire.as_bytes())

    inbound = parse_inbound_message(reparsed)
    assert len(inbound.attachments) == 1
    assert inbound.attachments[0].filename == "protokół.docx"
    assert inbound.attachments[0].content_type == DOCX
    assert inbound.attachments[0].data == b"PK\x03\x04zawartosc"


def test_rfc2047_encoded_filename_is_decoded() -> None:
    """A filename MIME delivers already RFC 2047 encoded — build it by hand rather
    than going through build_outbound_email, which only ever emits it pre-decoded."""
    raw = (
        b"From: a@example.test\r\n"
        b"To: b@example.test\r\n"
        b"Subject: test\r\n"
        b"Message-ID: <x@example.test>\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=BOUND\r\n"
        b"\r\n"
        b"--BOUND\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"body\r\n"
        b"--BOUND\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b"Content-Disposition: attachment; filename*=UTF-8''protok%C3%B3%C5%82.docx\r\n"
        b"\r\n"
        b"data\r\n"
        b"--BOUND--\r\n"
    )
    inbound = parse_inbound_message(email.message_from_bytes(raw))
    assert inbound.attachments[0].filename == "protokół.docx"


def test_threading_headers_point_at_the_original_client_message() -> None:
    """in_reply_to/references are threaded against the CLIENT's message id, never our
    own confirmation's — build_outbound_email must transmit exactly what it is given."""
    client_message_id = "<original-client-request@example.test>"
    outbound = OutboundMessage(
        to="klient@example.test",
        subject="Re: walidacja",
        body="wynik",
        in_reply_to=client_message_id,
        references=[client_message_id],
    )
    wire = build_outbound_email(outbound, mail_from="svc@example.test")

    assert wire["In-Reply-To"] == client_message_id
    assert wire["References"] == client_message_id
    # And never against the Message-ID this function itself just minted:
    assert wire["Message-ID"] != client_message_id


def test_auto_submitted_header_is_set_by_default() -> None:
    outbound = OutboundMessage(to="a@b.test", subject="s", body="b")
    wire = build_outbound_email(outbound, mail_from="svc@example.test")
    assert wire["Auto-Submitted"] == "auto-replied"


def test_auto_submitted_header_omitted_when_disabled() -> None:
    outbound = OutboundMessage(to="a@b.test", subject="s", body="b", auto_submitted=False)
    wire = build_outbound_email(outbound, mail_from="svc@example.test")
    assert wire["Auto-Submitted"] is None


def test_missing_date_header_falls_back_to_now_rather_than_crashing() -> None:
    raw = b"From: a@example.test\r\nTo: b@example.test\r\nSubject: s\r\n\r\nbody\r\n"
    inbound = parse_inbound_message(email.message_from_bytes(raw))
    assert inbound.received_at is not None


def test_unparseable_date_header_falls_back_to_now_rather_than_crashing() -> None:
    raw = (
        b"From: a@example.test\r\nTo: b@example.test\r\n"
        b"Subject: s\r\nDate: not-a-date\r\n\r\nbody\r\n"
    )
    inbound = parse_inbound_message(email.message_from_bytes(raw))
    assert inbound.received_at is not None


def test_date_header_with_an_explicit_offset_keeps_its_own_tzinfo() -> None:
    raw = (
        b"From: a@example.test\r\nTo: b@example.test\r\nSubject: s\r\n"
        b"Date: Mon, 30 Aug 2026 12:00:00 +0200\r\n\r\nbody\r\n"
    )
    inbound = parse_inbound_message(email.message_from_bytes(raw))
    assert inbound.received_at.utcoffset() is not None
    assert inbound.received_at.hour == 12  # not shifted to UTC by the fallback path


def test_missing_subject_decodes_to_empty_string_not_none() -> None:
    raw = b"From: a@example.test\r\nTo: b@example.test\r\n\r\nbody\r\n"
    inbound = parse_inbound_message(email.message_from_bytes(raw))
    assert inbound.subject == ""
