"""Transport-layer failures.

Deliberately loud: a poller that swallows a connection failure and returns an empty
list looks exactly like "no mail arrived", which the brief calls out as the most
expensive failure mode available here. `fetch_unseen`/`send` raise rather than return
a falsy result once every reconnect attempt has failed.
"""

from __future__ import annotations

__all__ = ["MailTransportConnectionError", "MailTransportError"]


class MailTransportError(Exception):
    """Base class for every error this package raises."""


class MailTransportConnectionError(MailTransportError):
    """Every reconnect attempt failed. The caller should treat this as "try again next
    cycle" — not as "the mailbox is empty" and not as a reason to crash the poller."""
