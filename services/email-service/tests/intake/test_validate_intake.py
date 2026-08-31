"""validate_intake — every row of the rule matrix (req 6, req 8).

Every rejection's `code` matches the matrix, and every `detail` names the fix, not
just the symptom.
"""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from intake_helpers import (
    MANIFEST_TEXT,
    derivative_zip_from_fixture,
    docx_attachment,
    make_inbound,
    zip_attachment,
    zip_bytes,
)

from email_service.intake import (
    ParsedRequest,
    RateLimiter,
    allowed_senders_from_env,
    parse_inbound,
    validate_intake,
)
from email_service.transport import Attachment

ALLOWED = frozenset({"client@example.test"})


def _parsed(**overrides: object) -> ParsedRequest:
    return parse_inbound(make_inbound(**overrides))


def test_valid_request_has_no_problems() -> None:
    parsed = _parsed(body=MANIFEST_TEXT, attachments=[docx_attachment("form.docx")])
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)
    assert verdict.valid is True
    assert verdict.problems == []


def test_display_name_sender_is_normalized_for_allowlist() -> None:
    parsed = _parsed(
        sender="Jan Frackowiak <client@example.test>",
        body=MANIFEST_TEXT,
        attachments=[docx_attachment("form.docx")],
    )
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)

    assert parsed.sender == "client@example.test"
    assert verdict.valid is True


def test_missing_manifest_when_body_is_empty() -> None:
    parsed = _parsed(body="", attachments=[docx_attachment("form.docx")])
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)
    assert verdict.valid is False
    codes = [p.code for p in verdict.problems]
    assert "missing_manifest" in codes
    detail = next(p.detail for p in verdict.problems if p.code == "missing_manifest")
    assert "body" in detail.lower()


def test_empty_manifest_when_body_is_whitespace_only() -> None:
    parsed = _parsed(body="   \n\t  ", attachments=[docx_attachment("form.docx")])
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)
    assert verdict.valid is False
    codes = [p.code for p in verdict.problems]
    assert "empty_manifest" in codes
    assert "missing_manifest" not in codes


def test_no_work_items_when_there_are_no_attachments() -> None:
    parsed = _parsed(body=MANIFEST_TEXT, attachments=[])
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)
    assert verdict.valid is False
    codes = [p.code for p in verdict.problems]
    assert "no_work_items" in codes
    detail = next(p.detail for p in verdict.problems if p.code == "no_work_items")
    assert ".docx" in detail


def test_unsupported_format_attachment() -> None:
    parsed = _parsed(
        body=MANIFEST_TEXT,
        attachments=[Attachment(filename="photo.png", content_type="image/png", data=b"\x89PNG")],
    )
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)
    assert verdict.valid is False
    problem = next(p for p in verdict.problems if p.code == "unsupported_format")
    assert "photo.png" in problem.detail


def test_empty_archive() -> None:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no forms")
    parsed = _parsed(
        body=MANIFEST_TEXT,
        attachments=[zip_attachment("derivative.zip", buf.getvalue())],
    )
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)
    assert verdict.valid is False
    problem = next(p for p in verdict.problems if p.code == "empty_archive")
    assert "derivative.zip" in problem.detail


def test_unstructured_inputs() -> None:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("loose.txt", "not in a folder")
    parsed = _parsed(
        body=MANIFEST_TEXT,
        attachments=[zip_attachment("net-new.zip", buf.getvalue())],
    )
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)
    assert verdict.valid is False
    problem = next(p for p in verdict.problems if p.code == "unstructured_inputs")
    assert "folder" in problem.detail.lower()


def test_unsafe_archive() -> None:
    malicious = zip_bytes({"../escape.docx": b"x"})
    parsed = _parsed(
        body=MANIFEST_TEXT,
        attachments=[zip_attachment("derivative.zip", malicious)],
    )
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)
    assert verdict.valid is False
    problem = next(p for p in verdict.problems if p.code == "unsafe_archive")
    assert "derivative.zip" in problem.detail


def test_archive_too_large() -> None:
    msg = make_inbound(
        body=MANIFEST_TEXT,
        attachments=[zip_attachment("derivative.zip", derivative_zip_from_fixture())],
    )
    parsed = parse_inbound(msg, max_archive_bytes=10)  # the fixture docx is far bigger
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)
    assert verdict.valid is False
    problem = next(p for p in verdict.problems if p.code == "archive_too_large")
    assert "derivative.zip" in problem.detail


def test_sender_not_allowed_when_allowlist_does_not_include_sender() -> None:
    parsed = _parsed(
        sender="stranger@example.test",
        body=MANIFEST_TEXT,
        attachments=[docx_attachment("form.docx")],
    )
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)
    assert verdict.valid is False
    problem = next(p for p in verdict.problems if p.code == "sender_not_allowed")
    assert "stranger@example.test" in problem.detail


def test_empty_allowed_senders_defaults_closed_not_open() -> None:
    """ALLOWED_SENDERS empty means CLOSED — nobody gets through, not everyone."""
    parsed = _parsed(
        sender="anyone@example.test",
        body=MANIFEST_TEXT,
        attachments=[docx_attachment("form.docx")],
    )
    verdict = validate_intake(parsed, allowed_senders=frozenset())
    assert verdict.valid is False
    assert any(p.code == "sender_not_allowed" for p in verdict.problems)


def test_allowed_senders_from_env_defaults_closed() -> None:
    assert allowed_senders_from_env({}) == frozenset()
    assert allowed_senders_from_env({"ALLOWED_SENDERS": ""}) == frozenset()
    assert allowed_senders_from_env({"ALLOWED_SENDERS": "a@x.test, B@X.test"}) == frozenset(
        {"a@x.test", "b@x.test"}
    )


def test_rate_limited_when_cap_exceeded() -> None:
    limiter = RateLimiter(max_requests=2, window=timedelta(hours=1))
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    parsed = _parsed(body=MANIFEST_TEXT, attachments=[docx_attachment("form.docx")])

    first = validate_intake(parsed, allowed_senders=ALLOWED, rate_limiter=limiter, now=now)
    second = validate_intake(parsed, allowed_senders=ALLOWED, rate_limiter=limiter, now=now)
    third = validate_intake(parsed, allowed_senders=ALLOWED, rate_limiter=limiter, now=now)

    assert first.valid is True
    assert second.valid is True
    assert third.valid is False
    problem = next(p for p in third.problems if p.code == "rate_limited")
    assert "client@example.test" in problem.detail


def test_rate_limiter_window_expires() -> None:
    limiter = RateLimiter(max_requests=1, window=timedelta(minutes=10))
    t0 = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    parsed = _parsed(body=MANIFEST_TEXT, attachments=[docx_attachment("form.docx")])

    first = validate_intake(parsed, allowed_senders=ALLOWED, rate_limiter=limiter, now=t0)
    second = validate_intake(parsed, allowed_senders=ALLOWED, rate_limiter=limiter, now=t0)
    later = validate_intake(
        parsed, allowed_senders=ALLOWED, rate_limiter=limiter, now=t0 + timedelta(minutes=11)
    )

    assert first.valid is True
    assert second.valid is False
    assert later.valid is True


def test_no_rate_limiter_means_no_cap_enforced() -> None:
    parsed = _parsed(body=MANIFEST_TEXT, attachments=[docx_attachment("form.docx")])
    for _ in range(50):
        verdict = validate_intake(parsed, allowed_senders=ALLOWED)
        assert verdict.valid is True


def test_disallowed_sender_is_not_rate_limited_first() -> None:
    """Do not spend rate-limit budget on senders we are going to reject anyway."""
    limiter = RateLimiter(max_requests=1)
    parsed = _parsed(
        sender="stranger@example.test",
        body=MANIFEST_TEXT,
        attachments=[docx_attachment("form.docx")],
    )
    verdict = validate_intake(parsed, allowed_senders=ALLOWED, rate_limiter=limiter)
    codes = [p.code for p in verdict.problems]
    assert codes == ["sender_not_allowed"]


def test_multiple_problems_all_reported_together() -> None:
    parsed = _parsed(sender="stranger@example.test", body="", attachments=[])
    verdict = validate_intake(parsed, allowed_senders=ALLOWED)
    codes = {p.code for p in verdict.problems}
    assert codes == {"sender_not_allowed", "missing_manifest", "no_work_items"}


def test_rate_limiter_rejects_non_positive_max_requests() -> None:
    with pytest.raises(ValueError, match="max_requests must be at least 1"):
        RateLimiter(max_requests=0)
