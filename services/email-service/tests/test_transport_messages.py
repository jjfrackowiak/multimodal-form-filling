"""The shared message shapes. B4 owns the module; these pin the contract B3 and B13 rely on."""

from __future__ import annotations

from datetime import UTC, datetime

from email_service.transport import Attachment, InboundMessage, OutboundMessage

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _inbound(**over: object) -> InboundMessage:
    base: dict[str, object] = {
        "message_id": "<abc@example.test>",
        "sender": "jot@example.test",
        "subject": "Walidacja",
        "body": "16 zdjęć,\nPod maską",
        "received_at": datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
    }
    return InboundMessage.model_validate({**base, **over})


def test_body_carries_the_manifest_verbatim() -> None:
    """The manifest is the body, never an attachment — including its newlines."""
    msg = _inbound()
    assert msg.body == "16 zdjęć,\nPod maską"
    assert msg.attachments == []


def test_attachment_filename_survives_utf8() -> None:
    """MIME may deliver this RFC 2047 encoded; by the time it is an Attachment it is decoded."""
    a = Attachment(filename="protokół.docx", content_type=DOCX, data=b"PK\x03\x04")
    assert a.filename == "protokół.docx"
    assert a.data.startswith(b"PK")


def test_headers_are_available_for_autoresponder_detection() -> None:
    """Never auto-reply to Auto-Submitted or List-Id — the loop-prevention rule."""
    msg = _inbound(headers={"Auto-Submitted": "auto-replied"})
    assert msg.headers["Auto-Submitted"] == "auto-replied"


def test_reply_threads_on_the_original_message() -> None:
    """in_reply_to is the CLIENT's id, never our own confirmation's."""
    out = OutboundMessage(
        to="jot@example.test",
        subject="Wynik walidacji",
        body="…",
        in_reply_to="<abc@example.test>",
        references=["<abc@example.test>"],
    )
    assert out.in_reply_to == "<abc@example.test>"
    assert out.references == ["<abc@example.test>"]


def test_replies_are_auto_submitted_by_default() -> None:
    """So another autoresponder does not answer us and loop forever."""
    assert OutboundMessage(to="x@y.test", subject="s", body="b").auto_submitted is True


def test_carries_arbitrary_binary_payloads() -> None:
    """A .docx is a zip — arbitrary bytes, not text. These stay in-process by design."""
    msg = _inbound(
        attachments=[Attachment(filename="f.docx", content_type=DOCX, data=b"PK\x03\x04\x00\xff")]
    )
    assert msg.attachments[0].data == b"PK\x03\x04\x00\xff"
