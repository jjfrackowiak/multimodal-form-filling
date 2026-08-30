"""render_rejection — req 6/8: every problem's code and fix-naming detail survive."""

from __future__ import annotations

from intake_helpers import MANIFEST_TEXT, make_inbound

from email_service.intake import parse_inbound
from email_service.replies import render_rejection
from mff_contracts import IntakeProblem, IntakeVerdict


def test_every_problem_code_and_detail_appear_in_the_body() -> None:
    verdict = IntakeVerdict(
        valid=False,
        problems=[
            IntakeProblem(code="missing_manifest", detail="Write the manifest in the body."),
            IntakeProblem(
                code="unsafe_archive",
                detail="'derivative.zip' contains an unsafe entry — remove it and re-zip.",
            ),
        ],
    )
    parsed = parse_inbound(make_inbound(body=""))

    out = render_rejection(verdict, parsed)

    assert "[missing_manifest]" in out.body
    assert "Write the manifest in the body." in out.body
    assert "[unsafe_archive]" in out.body
    assert "remove it and re-zip." in out.body


def test_no_documents_were_touched_is_stated() -> None:
    verdict = IntakeVerdict(
        valid=False,
        problems=[IntakeProblem(code="no_work_items", detail="Attach a .docx form.")],
    )
    parsed = parse_inbound(make_inbound(body=MANIFEST_TEXT))
    out = render_rejection(verdict, parsed)
    assert "No documents were reviewed" in out.body


def test_threads_on_the_original_message() -> None:
    verdict = IntakeVerdict(
        valid=False,
        problems=[IntakeProblem(code="empty_manifest", detail="Write something.")],
    )
    parsed = parse_inbound(make_inbound(message_id="<client-7@example.test>", body="  "))

    out = render_rejection(verdict, parsed)

    assert out.to == parsed.sender
    assert out.in_reply_to == "<client-7@example.test>"
    assert out.references == ["<client-7@example.test>"]
    assert out.auto_submitted is True
    assert out.subject.startswith("Re:")
