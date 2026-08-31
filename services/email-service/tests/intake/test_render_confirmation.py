"""render_confirmation — req 7: the reply quotes RequestAccepted.requirements, it does
not produce them.
"""

from __future__ import annotations

from intake_helpers import (
    MANIFEST_TEXT,
    derivative_zip_from_fixture,
    golden_requirements,
    make_inbound,
    netnew_zip_from_fixture,
    zip_attachment,
)

from email_service.intake import parse_inbound
from email_service.replies import render_confirmation
from mff_contracts import RequestAccepted


def test_confirmation_is_concise_and_defers_requirement_details() -> None:
    requirements = golden_requirements()
    assert len(requirements) == 10

    accepted = RequestAccepted(request_id="req-123", requirements=requirements)
    parsed = parse_inbound(
        make_inbound(
            body=MANIFEST_TEXT,
            attachments=[zip_attachment("derivative.zip", derivative_zip_from_fixture())],
        )
    )

    out = render_confirmation(accepted, parsed)

    assert out.html_body is not None
    assert "width=device-width" in out.html_body
    assert "10 requirement(s)" in out.body
    for requirement in requirements:
        assert requirement.id not in out.body
        assert requirement.text not in out.body
        assert requirement.source_span not in out.body
        assert requirement.id not in out.html_body
        assert requirement.text not in out.html_body


def test_job_counts_reflect_both_modes() -> None:
    accepted = RequestAccepted(request_id="req-123", requirements=[])
    parsed = parse_inbound(
        make_inbound(
            body=MANIFEST_TEXT,
            attachments=[
                zip_attachment("derivative.zip", derivative_zip_from_fixture()),
                zip_attachment("net-new.zip", netnew_zip_from_fixture()),
            ],
        )
    )

    out = render_confirmation(accepted, parsed)

    assert "1 form(s) to validate" in out.body
    assert "1 form(s) to compose" in out.body


def test_threads_on_the_original_message_not_itself() -> None:
    accepted = RequestAccepted(request_id="req-123", requirements=[])
    parsed = parse_inbound(make_inbound(message_id="<client-9@example.test>", body=MANIFEST_TEXT))

    out = render_confirmation(accepted, parsed)

    assert out.to == parsed.sender
    assert out.in_reply_to == "<client-9@example.test>"
    assert out.references == ["<client-9@example.test>"]
    assert out.auto_submitted is True


def test_subject_gets_a_re_prefix_once() -> None:
    accepted = RequestAccepted(request_id="req-123", requirements=[])

    parsed_plain = parse_inbound(make_inbound(subject="Zwrot pojazdu"))
    out_plain = render_confirmation(accepted, parsed_plain)
    assert out_plain.subject == "Re: Zwrot pojazdu"

    parsed_already = parse_inbound(make_inbound(subject="Re: Zwrot pojazdu"))
    out_already = render_confirmation(accepted, parsed_already)
    assert out_already.subject == "Re: Zwrot pojazdu"
    assert not out_already.subject.lower().startswith("re: re:")

    parsed_blank = parse_inbound(make_inbound(subject="   "))
    out_blank = render_confirmation(accepted, parsed_blank)
    assert out_blank.subject == "Re:"
