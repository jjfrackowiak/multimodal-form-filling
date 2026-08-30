"""The suite that must pass identically against InMemoryTransport and
ImapSmtpTransport — see CONTEXT.md: "if a test only passes in-memory, the real one is
untested and the Protocol bought nothing."

Every test takes `transport_harness` (conftest.py), which is parametrised over
`in_memory` (always) and `greenmail` (skipped automatically unless GreenMail is
reachable — see conftest.py and the report for whether it ran in this environment).

Covers definition-of-done items 2, 3, 4 and 6 from the brief.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from conftest import TransportHarness

from email_service.transport import Attachment, InboundMessage, OutboundMessage

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _inbound(
    marker: str, *, message_id: str | None = None, body: str | None = None
) -> InboundMessage:
    return InboundMessage(
        message_id=message_id or f"<{marker}@example.test>",
        sender="klient@example.test",
        subject=f"Validation [{marker}]",
        body=body or "16 photos,\nUnder the bonnet",
        received_at=datetime(2026, 8, 30, tzinfo=UTC),
    )


async def _fetch_marker(
    harness: TransportHarness, marker: str, *, attempts: int = 20, delay: float = 0.25
) -> InboundMessage:
    """Real delivery (GreenMail) is not instantaneous; the in-memory fake resolves on
    the first attempt, so this costs nothing there."""
    for _ in range(attempts):
        for message in await harness.transport.fetch_unseen():
            if marker in message.subject:
                return message
        await asyncio.sleep(delay)
    raise AssertionError(f"[{harness.name}] marker {marker!r} never arrived")


async def test_fetch_unseen_returns_a_delivered_message(
    transport_harness: TransportHarness,
) -> None:
    marker = uuid.uuid4().hex[:8]
    await transport_harness.deliver(_inbound(marker))

    fetched = await _fetch_marker(transport_harness, marker)
    assert "Under the bonnet" in fetched.body


async def test_mark_seen_excludes_the_message_from_a_later_fetch(
    transport_harness: TransportHarness,
) -> None:
    marker = uuid.uuid4().hex[:8]
    await transport_harness.deliver(_inbound(marker))
    fetched = await _fetch_marker(transport_harness, marker)

    await transport_harness.transport.mark_seen(fetched.message_id)

    remaining = [m for m in await transport_harness.transport.fetch_unseen() if marker in m.subject]
    assert remaining == []


async def test_the_same_message_id_delivered_twice_is_processed_once(
    transport_harness: TransportHarness,
) -> None:
    """Idempotency is keyed on Message-ID, not read state — see CONTEXT.md / the brief.
    Simulates a duplicate delivery (e.g. a Gmail sync artifact): same Message-ID,
    delivered twice."""
    marker = uuid.uuid4().hex[:8]
    message_id = f"<{marker}-dup@example.test>"
    await transport_harness.deliver(_inbound(marker, message_id=message_id, body="first"))
    await transport_harness.deliver(_inbound(marker, message_id=message_id, body="second copy"))

    matches: list[InboundMessage] = []
    for _ in range(20):
        matches = [
            m for m in await transport_harness.transport.fetch_unseen() if marker in m.subject
        ]
        if matches:
            break
        await asyncio.sleep(0.25)

    assert len(matches) == 1
    assert matches[0].message_id == message_id


async def test_send_preserves_polish_text_and_a_docx_attachment(
    transport_harness: TransportHarness,
) -> None:
    marker = uuid.uuid4().hex[:8]
    outbound = OutboundMessage(
        to=transport_harness.own_address,
        subject=f"Validation result [{marker}]",
        body="The form contains 4x seats and 2 vehicle diagonals — Under the bonnet OK.",
        attachments=[
            Attachment(filename="report.docx", content_type=DOCX, data=b"PK\x03\x04report-contents")
        ],
    )

    await transport_harness.transport.send(outbound)
    fetched = await _fetch_marker(transport_harness, marker)

    assert "vehicle diagonals" in fetched.body
    assert "Under the bonnet" in fetched.body
    assert len(fetched.attachments) == 1
    assert fetched.attachments[0].filename == "report.docx"
    assert fetched.attachments[0].data.startswith(b"PK\x03\x04")


async def test_send_threads_against_the_original_client_message(
    transport_harness: TransportHarness,
) -> None:
    marker = uuid.uuid4().hex[:8]
    client_message_id = f"<{marker}-original-client-message@example.test>"
    outbound = OutboundMessage(
        to=transport_harness.own_address,
        subject=f"Re: walidacja [{marker}]",
        body="wynik",
        in_reply_to=client_message_id,
        references=[client_message_id],
    )

    await transport_harness.transport.send(outbound)
    fetched = await _fetch_marker(transport_harness, marker)

    assert fetched.headers.get("In-Reply-To") == client_message_id
    assert client_message_id in fetched.headers.get("References", "")
