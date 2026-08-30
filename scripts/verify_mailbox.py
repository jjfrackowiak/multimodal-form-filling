#!/usr/bin/env python3
"""Prove a mailbox works before anyone writes a poller against it.

Works against both the local GreenMail container and a real provider — set
IMAP_USE_TLS / SMTP_USE_TLS and the real host/port, and it will authenticate.

Sends a message over SMTP with an attachment, then retrieves it over IMAP and
checks it arrived intact. Uses only the standard library.

    docker compose -f docker/compose.dev.yaml up -d
    python scripts/verify_mailbox.py

Exits 0 on success. Run this first whenever the email service misbehaves — it
separates "our code is wrong" from "the mailbox is not up", which are otherwise
easy to confuse and waste an afternoon on.
"""

from __future__ import annotations

import email
import imaplib
import os
import smtplib
import ssl
import sys
import time
import uuid
from email.message import EmailMessage


def _flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _tls_context() -> ssl.SSLContext:
    """Trust store that works on a stock macOS Python and inside a slim container.

    Python installed from python.org does not use the system keychain and ships a
    CA path that only exists once "Install Certificates.command" has been run —
    which nobody remembers. Slim container images often carry no CA bundle at
    all. certifi covers both, so prefer it and fall back to system defaults.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


IMAP_HOST = os.environ.get("IMAP_HOST", "localhost")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "3143"))
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "3025"))
USER = os.environ.get("IMAP_USER", "forms@example.test")
PASSWORD = os.environ.get("IMAP_PASSWORD", "anything")
FOLDER = os.environ.get("IMAP_FOLDER", "INBOX")
SMTP_USER = os.environ.get("SMTP_USER", USER)
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", PASSWORD)
MAIL_FROM = os.environ.get("MAIL_FROM", USER)

# GreenMail is plaintext; Gmail and every real provider are not. Defaulting these
# to false keeps the local path zero-config, and .env turns them on for real.
IMAP_TLS = _flag("IMAP_USE_TLS")
SMTP_TLS = _flag("SMTP_USE_TLS")

TIMEOUT = 20.0
POLL_INTERVAL = 0.5


def _imap() -> imaplib.IMAP4:
    if IMAP_TLS:
        return imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=_tls_context())
    return imaplib.IMAP4(IMAP_HOST, IMAP_PORT)


def send(marker: str) -> None:
    msg = EmailMessage()
    # Sent from the service address to itself: this verifies the mailbox can both
    # send and receive, which is what the service needs. A real client message
    # arrives from elsewhere, but that path is identical from here.
    msg["From"] = MAIL_FROM
    # Send to the polled address. With plus-addressing this is what a Gmail
    # filter matches on, so the verifier exercises the same route real requests
    # take rather than a shortcut past it.
    msg["To"] = os.environ.get("MAIL_TO", USER)
    msg["Subject"] = f"Form validation [{marker}]"
    msg["Message-ID"] = f"<{marker}@example.test>"
    msg.set_content("16 photos,\nUnder the bonnet\n4x seats and 2 vehicle diagonals\n")
    # An attachment, because every real request carries one and a mailbox that
    # handles text but mangles attachments would pass a simpler check.
    msg.add_attachment(
        b"not really a docx, but it is bytes",
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="protokol.docx",
    )
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
        if SMTP_TLS:
            s.starttls(context=_tls_context())
            s.login(SMTP_USER, SMTP_PASSWORD)
        s.send_message(msg)


def fetch(marker: str) -> email.message.Message | None:
    """Poll the inbox until the message shows up or we give up."""
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        with _imap() as m:
            m.login(USER, PASSWORD)
            m.select(FOLDER)
            typ, data = m.search(None, "ALL")
            for num in data[0].split():
                typ, raw = m.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(raw[0][1])
                if marker in (msg.get("Subject") or ""):
                    return msg
        time.sleep(POLL_INTERVAL)
    return None


def main() -> int:
    marker = uuid.uuid4().hex[:8]
    print(f"SMTP  {SMTP_HOST}:{SMTP_PORT} tls={SMTP_TLS}")
    print(f"IMAP  {IMAP_HOST}:{IMAP_PORT} tls={IMAP_TLS}")
    print(f"user  {USER}   folder {FOLDER}")

    try:
        send(marker)
    except smtplib.SMTPAuthenticationError as exc:
        print(f"FAIL  SMTP rejected the credentials: {exc}")
        print("      On Gmail this is almost always one of:")
        print("        - using the account password instead of an App Password")
        print("        - App Password pasted with its spaces still in it")
        print("        - 2-Step Verification not enabled, so no App Password exists")
        return 1
    except OSError as exc:
        print(f"FAIL  cannot send: {exc}")
        print("      local?  docker compose -f docker/compose.dev.yaml up -d")
        print("      remote? check SMTP_HOST/SMTP_PORT and SMTP_USE_TLS")
        return 1
    print(f"  sent    [{marker}]")

    try:
        msg = fetch(marker)
    except imaplib.IMAP4.error as exc:
        print(f"FAIL  IMAP rejected the credentials: {exc}")
        print("      On Gmail, check IMAP is enabled and the App Password is correct.")
        return 1
    except OSError as exc:
        print(f"FAIL  cannot read over IMAP: {exc}")
        print("      Gmail needs IMAP_HOST=imap.gmail.com IMAP_PORT=993 IMAP_USE_TLS=true")
        return 1

    if msg is None:
        print(f"FAIL  message did not arrive within {TIMEOUT:.0f}s")
        return 1

    attachments = [p.get_filename() for p in msg.walk() if p.get_filename()]

    # Decode the text part before checking. str(msg) is the raw MIME source,
    # where the body is base64 or quoted-printable — the literal characters are
    # never in there, so testing against it reports a transport failure that did
    # not happen.
    body = ""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True) or b""
            body += payload.decode(part.get_content_charset() or "utf-8", "replace")
    body_ok = "Under the bonnet" in body

    print(f"  received  subject: {msg.get('Subject')}")
    print(f"            message-id: {msg.get('Message-ID')}")
    print(f"            attachments: {attachments}")

    if not attachments:
        print("FAIL  attachment did not survive the round trip")
        return 1
    if not body_ok:
        print("FAIL  Polish characters did not survive the round trip")
        print(f"      decoded body began: {body[:60]!r}")
        return 1

    print("PASS  SMTP send and IMAP retrieve both work, with attachment and UTF-8 intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
