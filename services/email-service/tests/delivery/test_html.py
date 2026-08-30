"""HTML alternative of the results email — mobile-safe layout, same facts as plaintext."""

from __future__ import annotations

from email import message_from_bytes

from email_service.delivery import deliver
from email_service.mail_html import render_delivery_html
from email_service.transport.messages import OutboundMessage
from email_service.transport.mime import build_outbound_email, parse_inbound_message
from mff_contracts import (
    JobCursor,
    JobRecord,
    RequestRecord,
    RequestResult,
    Requirement,
    ReviewComment,
)
from mff_store import InMemoryBlobStore


async def _golden_outbound(
    requirements: list[Requirement],
    comments: list[ReviewComment],
    manifest: str,
) -> OutboundMessage:
    blobs = InMemoryBlobStore()
    blob_ref = await blobs.put(
        b"pretend .docx bytes",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        kind="reviewed",
    )
    job = JobRecord(
        job_id="job-1",
        request_id="req-1",
        form_id="form_supplied.docx",
        status="done",
        cursor=JobCursor(slice_index=2),
        document=blob_ref,
        summary={"pass": 8, "fail": 2},
        unverified=[],
    )
    request = RequestRecord(
        request_id="req-1",
        manifest_raw=manifest,
        requirements=requirements,
        job_ids=[job.job_id],
        reply_to="client@example.com",
        original_message_id="<original-client-message@example.com>",
        status="running",
    )
    result = RequestResult(
        request_id="req-1",
        status="done",
        documents=[blob_ref],
        requirements=requirements,
        summary={"pass": 8, "fail": 2},
        unverified=[],
        failed_forms=[],
    )
    return await deliver(result, request, blobs=blobs, comments=comments, jobs=[job])


async def test_html_carries_the_same_facts(
    fixture_requirements: list[Requirement],
    fixture_comments: list[ReviewComment],
    fixture_manifest_text: str,
) -> None:
    message = await _golden_outbound(fixture_requirements, fixture_comments, fixture_manifest_text)
    assert message.html_body is not None
    html = message.html_body
    assert "width=device-width" in html
    assert "max-width:100%" in html
    assert "max-width: 620px" in html
    assert "R-01" in html
    assert "R-04" in html
    assert "Suggestion" in html
    assert "form_supplied.docx" in html
    assert "Under the bonnet" in html
    assert 'class="stat"' in html
    assert "word-break" in html

    wire = build_outbound_email(message, mail_from="svc@example.test")
    types = {part.get_content_type() for part in wire.walk()}
    assert "text/plain" in types
    assert "text/html" in types


async def test_html_escapes_manifest_markup() -> None:
    req = Requirement(
        id="R-01",
        ordinal=1,
        text='Check <script>alert(1)</script> & "quotes"',
        source_span="<b>raw</b>",
        source_line=1,
    )
    result = RequestResult(
        request_id="req-x",
        status="done",
        documents=[],
        requirements=[req],
        summary={"pass": 0, "fail": 0},
        unverified=[],
        failed_forms=[],
    )
    html = render_delivery_html(result=result, comments=[], attached=[], linked=[])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;raw&lt;/b&gt;" in html


def test_html_groups_mixed_modes() -> None:
    result = RequestResult(
        request_id="req-mix",
        status="done",
        documents=[],
        requirements=[],
        summary={"pass": 1, "fail": 0},
        unverified=[],
        failed_forms=[],
    )
    html = render_delivery_html(
        result=result,
        comments=[],
        attached=[
            ("form.docx", "derivative", 2048),
            ("folder.docx", "net_new", 4096),
        ],
        linked=[],
    )
    assert "reviewed forms" in html
    assert "composed documents" in html


def test_html_alternative_does_not_break_plain_round_trip() -> None:
    body = "16 photos,\nUnder the bonnet\n4x seats and 2 vehicle diagonals\n"
    outbound = OutboundMessage(
        to="klient@example.test",
        subject="Validation result",
        body=body,
        html_body="<html><body><p>16 photos</p></body></html>",
    )
    wire = build_outbound_email(outbound, mail_from="svc@example.test")
    inbound = parse_inbound_message(message_from_bytes(wire.as_bytes()))
    assert inbound.body == outbound.body
