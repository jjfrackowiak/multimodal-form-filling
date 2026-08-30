"""The rule that stops two robots emailing each other forever.

`should_auto_reply` is a pure predicate over the headers a real mailer sets — it does
not decide whether a message is a *valid request* (that is B3's job) and it does not
stop us ingesting the message (we always fetch it). It only gates whether an automated
reply should be composed and sent at all.

Checked BEFORE composing a reply, by whoever builds the `OutboundMessage` (B3/B13);
`MailTransport.send` transmits whatever it is given and does not consult this itself,
because a transport with an opinion about which messages deserve an answer is no
longer just moving bytes.
"""

from __future__ import annotations

from .messages import InboundMessage

__all__ = ["should_auto_reply"]


def should_auto_reply(message: InboundMessage) -> bool:
    """False for anything that looks like it came from another automated system.

    Three signals, any one of which is disqualifying:

    - ``Auto-Submitted`` starting with ``auto-`` (RFC 3834) — ``auto-replied``,
      ``auto-generated``, ``auto-notified``, .... ``Auto-Submitted: no`` is the
      normal, human case and does *not* disqualify.
    - A ``List-Id`` header — mailing lists and bulk senders carry one; a human
      correspondent's mail client never sets it.
    - A null return path (``Return-Path: <>``) — the convention bounce and
      notification systems use to say "do not reply to this address".
    """
    headers = {key.lower(): value for key, value in message.headers.items()}

    auto_submitted = headers.get("auto-submitted", "").strip().lower()
    if auto_submitted.startswith("auto-"):
        return False

    if "list-id" in headers:
        return False

    null_return_path = "return-path" in headers and headers["return-path"].strip() in {"", "<>"}
    return not null_return_path
