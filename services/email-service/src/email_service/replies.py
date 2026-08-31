"""Render the two replies intake ever sends — reqs 6, 7, 8.

**`render_confirmation` quotes `RequestAccepted.requirements`; it does not produce
them.** The editor parses the manifest exactly once and hands back the parsed list in
the 202 — this module's only job is to put that list, verbatim, in front of the client
so req 7 ("the confirmation reply carries the parsed requirement list") means what it
says: the list the client sees is the same list their document will be graded against,
not a second, possibly different, parse of the same text.

Both replies thread on the client's *original* message (`ParsedRequest.message_id`),
never on each other — `OutboundMessage.in_reply_to`/`references` exist for exactly this,
see `transport/messages.py`.
"""

from __future__ import annotations

from mff_contracts import IntakeVerdict, Mode, RequestAccepted

from .intake import ParsedRequest
from .mail_html import render_confirmation_html, render_rejection_html
from .transport import OutboundMessage

__all__ = ["render_confirmation", "render_rejection"]


def _reply_subject(original: str) -> str:
    stripped = " ".join(original.split())
    if not stripped:
        return "Re:"
    if stripped.lower().startswith("re:"):
        return stripped
    return f"Re: {stripped}"


def render_confirmation(accepted: RequestAccepted, req: ParsedRequest) -> OutboundMessage:
    """The 202 reply confirms receipt before the final delivery email."""
    derivative_jobs = [job for job in req.jobs if job.mode == Mode.DERIVATIVE]
    net_new_jobs = [job for job in req.jobs if job.mode == Mode.NET_NEW]

    lines = [
        "Your request has been received and accepted.",
        "",
        f"Request ID: {accepted.request_id}",
        (
            f"{len(derivative_jobs)} form(s) to validate, {len(net_new_jobs)} form(s) "
            f"to compose from supplied inputs ({len(req.jobs)} job(s) total)."
        ),
        "",
        f"{len(accepted.requirements)} requirement(s) were read from your manifest.",
        "The parsed requirements document and reviewed output will follow in a separate "
        "email once every job has finished running.",
    ]

    return OutboundMessage(
        to=req.sender,
        subject=_reply_subject(req.subject),
        body="\n".join(lines),
        html_body=render_confirmation_html(
            request_id=accepted.request_id,
            n_derivative=len(derivative_jobs),
            n_net_new=len(net_new_jobs),
            n_jobs=len(req.jobs),
            requirements=accepted.requirements,
        ),
        in_reply_to=req.message_id,
        references=[req.message_id],
    )


def render_rejection(verdict: IntakeVerdict, req: ParsedRequest) -> OutboundMessage:
    """The bounce reply. Every problem's `detail` names exactly what to add or change
    (req 6/8) — nothing here summarises or drops one.
    """
    lines = [
        "Your request could not be processed.",
        "",
        "Please fix the following and resend:",
        "",
    ]
    for problem in verdict.problems:
        lines.append(f"  [{problem.code}] {problem.detail}")
    lines.append("")
    lines.append("No documents were reviewed and nothing was changed.")

    return OutboundMessage(
        to=req.sender,
        subject=_reply_subject(req.subject),
        body="\n".join(lines),
        html_body=render_rejection_html(
            problems=[(problem.code, problem.detail) for problem in verdict.problems]
        ),
        in_reply_to=req.message_id,
        references=[req.message_id],
    )
