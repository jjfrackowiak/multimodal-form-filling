"""Behaviour specific to InMemoryTransport's role as a test seam — the shared suite in
test_protocol_suite.py covers everything it has in common with ImapSmtpTransport.
"""

from __future__ import annotations

from datetime import UTC, datetime

from email_service.transport import InboundMessage, InMemoryTransport, OutboundMessage


def _inbound(message_id: str) -> InboundMessage:
    return InboundMessage(
        message_id=message_id,
        sender="klient@example.test",
        subject="Validation",
        body="body text",
        received_at=datetime(2026, 8, 30, tzinfo=UTC),
    )


async def test_deliver_makes_a_message_fetchable() -> None:
    transport = InMemoryTransport()
    transport.deliver(_inbound("<a@example.test>"))

    fetched = await transport.fetch_unseen()
    assert [m.message_id for m in fetched] == ["<a@example.test>"]


async def test_sent_list_records_every_send_regardless_of_recipient() -> None:
    transport = InMemoryTransport(own_address="svc@example.test")
    outbound = OutboundMessage(to="someone-else@example.test", subject="s", body="b")

    await transport.send(outbound)

    assert transport.sent == [outbound]
    # Not addressed to our own mailbox, so it does not echo into fetch_unseen.
    assert await transport.fetch_unseen() == []


async def test_send_to_own_address_is_not_required_to_echo_when_unconfigured() -> None:
    """Without `own_address`, InMemoryTransport still records the send but has no
    mailbox of its own to echo into — this is what a fake with no self-notion does."""
    transport = InMemoryTransport()
    await transport.send(OutboundMessage(to="whoever@example.test", subject="s", body="b"))
    assert await transport.fetch_unseen() == []
