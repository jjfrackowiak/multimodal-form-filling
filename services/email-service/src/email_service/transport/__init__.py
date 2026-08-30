"""Mail transport. B4 owns the protocol and its implementations.

`ImapSmtpTransport` for real servers, `InMemoryTransport` as the fake everyone else
(B3, B5, B13) tests against — both satisfy `MailTransport` and both pass the same
parametrised suite (`tests/transport/test_protocol_suite.py`).
"""

from __future__ import annotations

from .config import ImapSmtpConfig
from .errors import MailTransportConnectionError, MailTransportError
from .imap_smtp import ImapSmtpTransport
from .in_memory import InMemoryTransport
from .loop_guard import should_auto_reply
from .messages import Attachment, InboundMessage, OutboundMessage
from .protocol import MailTransport

__all__ = [
    "Attachment",
    "ImapSmtpConfig",
    "ImapSmtpTransport",
    "InMemoryTransport",
    "InboundMessage",
    "MailTransport",
    "MailTransportConnectionError",
    "MailTransportError",
    "OutboundMessage",
    "should_auto_reply",
]
