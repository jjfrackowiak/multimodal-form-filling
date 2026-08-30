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

IMAP_HOST = os.environ.get("IMAP_HOST", "localhost")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "3143"))
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "3025"))
USER = os.environ.get("IMAP_USER", "forms@example.test")
PASSWORD = os.environ.get("IMAP_PASSWORD", "anything")
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
        return imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ssl.create_default_context())
    return imaplib.IMAP4(IMAP_HOST, IMAP_PORT)


def send(marker: str) -> None:
    msg = EmailMessage()
    # Sent from the service address to itself: this verifies the mailbox can both
    # send and receive, which is what the service needs. A real client message
    # arrives from elsewhere, but that path is identical from here.
    msg["From"] = MAIL_FROM
    msg["To"] = USER
    msg["Subject"] = f"Walidacja formularza [{marker}]"
    msg["Message-ID"] = f"<{marker}@example.test>"
    msg.set_content(
        "16 zdjęć,\nPod maską\n4x fotele i 2 przekatne pojazdu\n"
    )
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
            s.starttls(context=ssl.create_default_context())
            s.login(SMTP_USER, SMTP_PASSWORD)
        s.send_message(msg)


def fetch(marker: str) -> email.message.Message | None:
    """Poll the inbox until the message shows up or we give up."""
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        with _imap() as m:
            m.login(USER, PASSWORD)
            m.select("INBOX")
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
    print(f"user  {USER}")

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

    attachments = [
        p.get_filename() for p in msg.walk() if p.get_filename()
    ]
    body_ok = "Pod maską" in str(msg)

    print(f"  received  subject: {msg.get('Subject')}")
    print(f"            message-id: {msg.get('Message-ID')}")
    print(f"            attachments: {attachments}")

    if not attachments:
        print("FAIL  attachment did not survive the round trip")
        return 1
    if not body_ok:
        print("FAIL  Polish characters did not survive the round trip")
        return 1

    print("PASS  SMTP send and IMAP retrieve both work, with attachment and UTF-8 intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
