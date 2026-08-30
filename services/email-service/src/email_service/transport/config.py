"""Runtime configuration for `ImapSmtpTransport`.

Credentials are injected at runtime — `from_env()` reads them from the environment at
call time, never a baked-in default with a real secret. The defaults that *do* exist
(`localhost`, GreenMail's ports) only ever resolve to something real when the caller's
own environment sets them, which is exactly the local-dev / CI-with-Docker case.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = ["ImapSmtpConfig"]


def _flag(env: Mapping[str, str], name: str, default: str) -> bool:
    return env.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ImapSmtpConfig:
    """One place to change `IMAP_FOLDER`, `SMTP_PORT`, and so on — no code path below
    this class ever hardcodes a folder name or a port.

    `smtp_port` defaults to 587, never 25: GCP blocks outbound port 25 permanently,
    with no exceptions, and a fallback to it works locally and fails silently the
    moment this service is deployed. There is deliberately no fallback path to 25
    anywhere in this package.
    """

    imap_host: str
    imap_port: int = 993
    imap_use_tls: bool = True
    imap_user: str = ""
    imap_password: str = ""
    # Gmail exposes labels as IMAP folders — a filter routing mail to a dedicated
    # label lets the poller read only that label. Configuration, never an assumption.
    folder: str = "INBOX"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_use_tls: bool = True  # STARTTLS on 587, per the brief — never plaintext 25.
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ImapSmtpConfig:
        e = env if env is not None else os.environ
        imap_user = e.get("IMAP_USER", "")
        imap_password = e.get("IMAP_PASSWORD", "")
        return cls(
            imap_host=e.get("IMAP_HOST", "localhost"),
            imap_port=int(e.get("IMAP_PORT", "993")),
            imap_use_tls=_flag(e, "IMAP_USE_TLS", "true"),
            imap_user=imap_user,
            imap_password=imap_password,
            folder=e.get("IMAP_FOLDER", "INBOX"),
            smtp_host=e.get("SMTP_HOST", e.get("IMAP_HOST", "localhost")),
            smtp_port=int(e.get("SMTP_PORT", "587")),
            smtp_use_tls=_flag(e, "SMTP_USE_TLS", "true"),
            smtp_user=e.get("SMTP_USER", imap_user),
            smtp_password=e.get("SMTP_PASSWORD", imap_password),
            mail_from=e.get("MAIL_FROM", imap_user),
        )
