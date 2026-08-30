"""should_auto_reply — the rule that stops two robots emailing each other forever."""

from __future__ import annotations

from datetime import UTC, datetime

from email_service.transport import InboundMessage, should_auto_reply


def _inbound(**headers: str) -> InboundMessage:
    return InboundMessage(
        message_id="<msg@example.test>",
        sender="someone@example.test",
        subject="Validation",
        body="body text",
        received_at=datetime(2026, 8, 30, tzinfo=UTC),
        headers=headers,
    )


def test_ordinary_message_may_be_replied_to() -> None:
    assert should_auto_reply(_inbound()) is True


def test_auto_submitted_auto_replied_blocks_reply() -> None:
    assert should_auto_reply(_inbound(**{"Auto-Submitted": "auto-replied"})) is False


def test_auto_submitted_auto_generated_blocks_reply() -> None:
    assert should_auto_reply(_inbound(**{"Auto-Submitted": "auto-generated"})) is False


def test_auto_submitted_no_is_the_normal_case_and_allows_reply() -> None:
    """RFC 3834: `Auto-Submitted: no` is the *default*, human-sent value."""
    assert should_auto_reply(_inbound(**{"Auto-Submitted": "no"})) is True


def test_list_id_header_blocks_reply() -> None:
    assert should_auto_reply(_inbound(**{"List-Id": "<forms.example.test>"})) is False


def test_null_return_path_blocks_reply() -> None:
    assert should_auto_reply(_inbound(**{"Return-Path": "<>"})) is False


def test_missing_return_path_header_does_not_block_reply() -> None:
    """No Return-Path at all is not the same as a *null* one — most legitimate mail
    from a normal mail client will not carry this header at intake time."""
    assert should_auto_reply(_inbound()) is True


def test_header_matching_is_case_insensitive() -> None:
    assert should_auto_reply(_inbound(**{"auto-submitted": "auto-replied"})) is False
