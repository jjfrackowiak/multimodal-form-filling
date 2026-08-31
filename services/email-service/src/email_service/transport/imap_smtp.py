"""The real transport: IMAP for receiving, SMTP for sending.

**Connection strategy.** Gmail closes an idle IMAP connection around the 29-minute
mark, and a poller that holds one open and assumes it stays open works for twenty
minutes and then quietly stops — which looks exactly like "no mail arrived", the most
expensive failure mode available here. Rather than hold a long-lived connection and
re-issue `IDLE` against a clock, every operation here opens its own short-lived
connection and closes it when done. There is no connection old enough to be dropped
out from under a poll, which does not mitigate the 29-minute failure mode — it removes
the condition that causes it. `_max_retries` covers the remaining case: the connection
attempt itself, or the operation, is disrupted mid-flight (a network blip, the server
resetting a socket) — that gets one fresh reconnect, not a silent empty result.

**Idempotency** is a local ledger of `Message-ID`s passed to `mark_seen`, never the
server's `\\Seen` flag — Gmail's IMAP folders are labels and its read-state semantics
do not match a conventional server's, so a design that trusted the flag would be wrong
on the one provider this has to work against for real. `SEARCH UNSEEN` is only a
candidate filter so a Cloud Run restart does not re-download and re-process the
whole mailbox; the ledger still decides "already handled" within one process.
"""

from __future__ import annotations

import asyncio
import contextlib
import email
import imaplib
import smtplib
import ssl
from collections.abc import Iterator

from .config import ImapSmtpConfig
from .errors import MailTransportConnectionError, MailTransportError
from .messages import InboundMessage, OutboundMessage
from .mime import build_outbound_email, parse_inbound_message

__all__ = ["ImapSmtpTransport"]


def _tls_context() -> ssl.SSLContext:
    """certifi's bundle when available, falling back to the system trust store.

    A python.org macOS install does not use the system keychain and its own CA path
    only exists once "Install Certificates.command" has been run; a slim container
    image often ships no CA bundle at all. certifi covers both.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _sequence_numbers(search_data: list[bytes]) -> list[str]:
    """`IMAP4.search`'s payload is untyped in typeshed (`list[Any]`); narrow it back
    to what a real server sends — a single space-separated line of message numbers —
    and decode each to the `str` `fetch`/`store` actually expect."""
    if not search_data or not isinstance(search_data[0], bytes):
        return []
    return [num.decode("ascii") for num in search_data[0].split()]


class ImapSmtpTransport:
    def __init__(
        self,
        config: ImapSmtpConfig,
        *,
        max_retries: int = 2,
        timeout: float = 20.0,
    ) -> None:
        self._config = config
        self._max_retries = max_retries
        self._timeout = timeout
        # Idempotency ledger — see module docstring. In-process only: this transport
        # does not own persistence (that is mff-store's job for anything that must
        # survive a restart); it guarantees "not reprocessed within one process's
        # lifetime without an explicit mark_seen", which is what the Protocol promises.
        self._seen_ids: set[str] = set()

    # -- MailTransport -----------------------------------------------------

    async def fetch_unseen(self) -> list[InboundMessage]:
        return await asyncio.to_thread(self._fetch_unseen_sync)

    async def mark_seen(self, message_id: str) -> None:
        self._seen_ids.add(message_id)
        # Best-effort hygiene so a human glancing at the mailbox sees it as read.
        # Never the source of truth — idempotency lives in `_seen_ids` above, exactly
        # because Gmail's \\Seen semantics cannot be trusted to mean "processed".
        await asyncio.to_thread(self._flag_seen_best_effort, message_id)

    async def send(self, message: OutboundMessage) -> None:
        await asyncio.to_thread(self._send_sync, message)

    # -- IMAP, off the event loop thread ------------------------------------

    @contextlib.contextmanager
    def _imap_connect(self) -> Iterator[imaplib.IMAP4]:
        c = self._config
        imap: imaplib.IMAP4
        if c.imap_use_tls:
            imap = imaplib.IMAP4_SSL(
                c.imap_host, c.imap_port, ssl_context=_tls_context(), timeout=self._timeout
            )
        else:
            imap = imaplib.IMAP4(c.imap_host, c.imap_port, timeout=self._timeout)
        try:
            imap.login(c.imap_user, c.imap_password)
            yield imap
        finally:
            with contextlib.suppress(Exception):
                imap.logout()

    def _fetch_unseen_sync(self) -> list[InboundMessage]:
        last_exc: Exception | None = None
        for _attempt in range(self._max_retries + 1):
            try:
                return self._fetch_once()
            except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError, MailTransportError) as exc:
                # Covers a dropped socket (abort/error/OSError) *and* a non-OK SELECT
                # or SEARCH response (MailTransportError) — either way, the connection
                # this attempt opened is discarded and the next iteration opens an
                # entirely new one. That is the reconnect.
                last_exc = exc
                continue
        raise MailTransportConnectionError(
            f"IMAP fetch failed after {self._max_retries + 1} attempt(s) "
            f"against {self._config.imap_host}:{self._config.imap_port}"
        ) from last_exc

    def _fetch_once(self) -> list[InboundMessage]:
        with self._imap_connect() as imap:
            typ, _data = imap.select(self._config.folder)
            if typ != "OK":
                raise MailTransportError(f"cannot select folder {self._config.folder!r}")

            typ, data = imap.search(None, "UNSEEN")
            if typ != "OK":
                raise MailTransportError("IMAP SEARCH failed")

            found: dict[str, InboundMessage] = {}
            for num in _sequence_numbers(data):
                # RFC822 marks a Gmail message seen as a side effect. A restart during
                # orchestration must leave it eligible for a fresh poll and recovery.
                typ, raw = imap.fetch(num, "(BODY.PEEK[])")
                if typ != "OK" or not raw:
                    continue
                first = raw[0]
                if not isinstance(first, tuple) or not isinstance(first[1], bytes):
                    continue
                parsed = parse_inbound_message(email.message_from_bytes(first[1]))
                if parsed.message_id in self._seen_ids:
                    continue
                # Same Message-ID under two UIDs (e.g. a duplicate delivery) collapses
                # to one entry — idempotency within a single batch, not just across
                # fetch_unseen calls.
                found.setdefault(parsed.message_id, parsed)
            return list(found.values())

    def _flag_seen_best_effort(self, message_id: str) -> None:
        with contextlib.suppress(Exception), self._imap_connect() as imap:
            imap.select(self._config.folder)
            typ, data = imap.search(None, "HEADER", "Message-ID", message_id)
            if typ != "OK":
                return
            for num in _sequence_numbers(data):
                imap.store(num, "+FLAGS", "\\Seen")

    # -- SMTP, off the event loop thread ------------------------------------

    @contextlib.contextmanager
    def _smtp_connect(self) -> Iterator[smtplib.SMTP]:
        c = self._config
        # 465 is implicit TLS (SMTPS). 587 is STARTTLS. Never 25 (GCP blocks it).
        if c.smtp_port == 465:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                c.smtp_host, c.smtp_port, timeout=self._timeout, context=_tls_context()
            )
        else:
            smtp = smtplib.SMTP(c.smtp_host, c.smtp_port, timeout=self._timeout)
            if c.smtp_use_tls:
                smtp.starttls(context=_tls_context())
        try:
            if c.smtp_user:
                smtp.login(c.smtp_user, c.smtp_password)
            yield smtp
        finally:
            with contextlib.suppress(Exception):
                smtp.quit()

    def _send_sync(self, message: OutboundMessage) -> None:
        c = self._config
        mail_from = c.mail_from or c.smtp_user or c.imap_user
        email_msg = build_outbound_email(message, mail_from=mail_from)

        last_exc: Exception | None = None
        for _attempt in range(self._max_retries + 1):
            try:
                with self._smtp_connect() as smtp:
                    smtp.send_message(email_msg)
                return
            except (smtplib.SMTPServerDisconnected, OSError) as exc:
                last_exc = exc
                continue
        raise MailTransportConnectionError(
            f"SMTP send failed after {self._max_retries + 1} attempt(s) "
            f"against {c.smtp_host}:{c.smtp_port}"
        ) from last_exc
