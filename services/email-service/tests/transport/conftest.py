"""Shared harness for the parametrised transport suite.

`transport_harness` is parametrised over `["in_memory", "greenmail"]`. `in_memory`
always runs — no Docker, no network — and `greenmail` runs only when
`docker/compose.dev.yaml`'s GreenMail container is actually reachable on the ports
below, mirroring exactly how `packages/mff-store/tests/conftest.py` treats the
Firestore/GCS emulators: skipped, not failed, so `make check` stays green offline.

    docker compose -f docker/compose.dev.yaml up -d greenmail
    uv run pytest services/email-service/tests -q

A test written against `transport_harness` runs against both backends automatically —
see CONTEXT.md: "if a test only passes in-memory, the real one is untested and the
Protocol bought nothing."
"""

from __future__ import annotations

import os
import smtplib
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import pytest
import pytest_asyncio

from email_service.transport import (
    ImapSmtpConfig,
    ImapSmtpTransport,
    InMemoryTransport,
    MailTransport,
)
from email_service.transport.messages import InboundMessage
from email_service.transport.mime import build_outbound_email

GREENMAIL_IMAP_HOST = os.environ.get("GREENMAIL_IMAP_HOST", "localhost")
GREENMAIL_IMAP_PORT = int(os.environ.get("GREENMAIL_IMAP_PORT", "3143"))
GREENMAIL_SMTP_HOST = os.environ.get("GREENMAIL_SMTP_HOST", "localhost")
GREENMAIL_SMTP_PORT = int(os.environ.get("GREENMAIL_SMTP_PORT", "3025"))
GREENMAIL_ADDRESS = "forms@example.test"


def _reachable(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def greenmail_available() -> bool:
    return _reachable(GREENMAIL_IMAP_HOST, GREENMAIL_IMAP_PORT) and _reachable(
        GREENMAIL_SMTP_HOST, GREENMAIL_SMTP_PORT
    )


@dataclass
class TransportHarness:
    """One handle both backends satisfy identically for the shared suite."""

    name: str
    transport: MailTransport
    own_address: str
    deliver: Callable[[InboundMessage], Awaitable[None]]


def _make_in_memory_harness() -> TransportHarness:
    own_address = "svc@in-memory.test"
    transport = InMemoryTransport(own_address=own_address)

    async def deliver(message: InboundMessage) -> None:
        transport.deliver(message)

    return TransportHarness(
        name="in_memory", transport=transport, own_address=own_address, deliver=deliver
    )


def _make_greenmail_harness() -> TransportHarness:
    own_address = GREENMAIL_ADDRESS
    config = ImapSmtpConfig(
        imap_host=GREENMAIL_IMAP_HOST,
        imap_port=GREENMAIL_IMAP_PORT,
        imap_use_tls=False,
        imap_user=own_address,
        imap_password="anything",  # GreenMail runs with auth disabled
        folder="INBOX",
        smtp_host=GREENMAIL_SMTP_HOST,
        smtp_port=GREENMAIL_SMTP_PORT,
        smtp_use_tls=False,
        smtp_user=own_address,
        smtp_password="anything",
        mail_from=own_address,
    )
    transport = ImapSmtpTransport(config, timeout=10.0)

    async def deliver(message: InboundMessage) -> None:
        # Reuses the same OutboundMessage -> MIME builder production code uses, so
        # this is not a second, parallel MIME implementation to keep in sync — it is
        # the identical wire path `send()` takes, just injected with a fixed
        # Message-ID and headers so the delivered copy matches `message` exactly.
        from email_service.transport.messages import OutboundMessage

        outbound = OutboundMessage(to=own_address, subject=message.subject, body=message.body)
        email_msg = build_outbound_email(outbound, mail_from=message.sender or own_address)
        del email_msg["Message-ID"]
        email_msg["Message-ID"] = message.message_id
        for key, value in message.headers.items():
            if key in email_msg:
                del email_msg[key]
            email_msg[key] = value
        for attachment in message.attachments:
            maintype, _, subtype = attachment.content_type.partition("/")
            email_msg.add_attachment(
                attachment.data,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=attachment.filename,
            )
        with smtplib.SMTP(GREENMAIL_SMTP_HOST, GREENMAIL_SMTP_PORT, timeout=15) as smtp:
            smtp.send_message(email_msg)

    return TransportHarness(
        name="greenmail", transport=transport, own_address=own_address, deliver=deliver
    )


_greenmail_param = pytest.param(
    "greenmail",
    marks=pytest.mark.skipif(
        not greenmail_available(),
        reason="GreenMail not reachable — docker compose -f docker/compose.dev.yaml up -d",
    ),
)


@pytest_asyncio.fixture(params=["in_memory", _greenmail_param])
async def transport_harness(request: pytest.FixtureRequest) -> AsyncIterator[TransportHarness]:
    if request.param == "in_memory":
        yield _make_in_memory_harness()
        return
    yield _make_greenmail_harness()
