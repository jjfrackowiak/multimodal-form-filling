#!/usr/bin/env python3
"""Prove the local mailbox works before anyone writes a poller against it.

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
import sys
import time
import uuid
from email.message import EmailMessage

IMAP_HOST = os.environ.get("IMAP_HOST", "localhost")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "3143"))
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "3025"))
USER = os.environ.get("IMAP_USER", "forms@example.test")
PASSWORD = os.environ.get("IMAP_PASSWORD", "anything")

TIMEOUT = 20.0
POLL_INTERVAL = 0.5


def send(marker: str) -> None:
    msg = EmailMessage()
    msg["From"] = "client@example.test"
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
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
        s.send_message(msg)


def fetch(marker: str) -> email.message.Message | None:
    """Poll the inbox until the message shows up or we give up."""
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        with imaplib.IMAP4(IMAP_HOST, IMAP_PORT) as m:
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
    print(f"SMTP  {SMTP_HOST}:{SMTP_PORT}   IMAP  {IMAP_HOST}:{IMAP_PORT}   user {USER}")

    try:
        send(marker)
    except OSError as exc:
        print(f"FAIL  cannot send: {exc}")
        print("      is the mail server up?  docker compose -f docker/compose.dev.yaml up -d")
        return 1
    print(f"  sent    [{marker}]")

    try:
        msg = fetch(marker)
    except OSError as exc:
        print(f"FAIL  cannot read over IMAP: {exc}")
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
