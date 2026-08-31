"""ImapSmtpTransport's own machinery, tested with fakes standing in for imaplib /
smtplib — no socket, no Docker.

This is where DoD-5 (reconnect rather than a silent stop) lives: every attempt inside
`_fetch_unseen_sync` opens a brand-new connection object (a fresh `_FakeImap4`
instance below, exactly like a fresh `imaplib.IMAP4` in production), so "kill the
connection mid-poll" is modelled as the first instance failing and a *different*,
freshly-constructed instance succeeding — proving the retry is a real reconnect, not
a retry against the same dead socket.
"""

from __future__ import annotations

import asyncio
import email.message
import imaplib
import smtplib
from collections.abc import Callable
from typing import ClassVar

import pytest

from email_service.transport import (
    ImapSmtpConfig,
    ImapSmtpTransport,
    MailTransportConnectionError,
    OutboundMessage,
)
from email_service.transport.imap_smtp import _sequence_numbers

# Patched on the real `imaplib`/`smtplib` modules, not on `imap_smtp`'s reference to
# them — `imap_smtp.py` does `import imaplib`, which binds the *same* module object,
# so patching it here is visible there too, without reaching into another module's
# (unexported) attributes.


def _raw_message(message_id: str = "<m@example.test>") -> bytes:
    msg = email.message.EmailMessage()
    msg["From"] = "klient@example.test"
    msg["To"] = "svc@example.test"
    msg["Subject"] = "Validation"
    msg["Message-ID"] = message_id
    msg.set_content("body text")
    return msg.as_bytes()


class _FakeImap4:
    """Stands in for `imaplib.IMAP4`. `on_select` lets a test inject failure/recording
    behaviour per constructed instance — each construction is a fresh "connection",
    which is the thing the reconnect logic is supposed to produce.

    `abort`/`error` are the *real* exception classes (captured before any
    monkeypatching) so that every subclass below — whatever gets assigned to
    `imaplib.IMAP4` in a given test — still satisfies `ImapSmtpTransport`'s
    `except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError)`, which resolves
    those names dynamically off of whatever `imaplib.IMAP4` currently is.
    """

    abort = imaplib.IMAP4.abort
    error = imaplib.IMAP4.error

    instances: ClassVar[list[_FakeImap4]] = []

    def __init__(
        self,
        host: str,
        port: int,
        *args: object,
        raw_message: bytes = b"",
        on_select: Callable[[_FakeImap4], None] | None = None,
        **kwargs: object,
    ) -> None:
        self.host = host
        self.port = port
        self._raw_message = raw_message
        self._on_select = on_select
        self.selected: str | None = None
        self.search_criteria: tuple[str, ...] = ()
        _FakeImap4.instances.append(self)

    def login(self, user: str, password: str) -> tuple[str, list[bytes]]:
        return "OK", [b"done"]

    def select(self, folder: str = "INBOX", readonly: bool = False) -> tuple[str, list[bytes]]:
        self.selected = folder
        if self._on_select is not None:
            self._on_select(self)
        return "OK", [b"1"]

    def search(self, charset: str | None, *criteria: str) -> tuple[str, list[bytes]]:
        self.search_criteria = criteria
        return "OK", [b"1"]

    def fetch(self, num: str, parts: str) -> tuple[str, list[tuple[bytes, bytes] | None]]:
        assert parts == "(BODY.PEEK[])"
        return "OK", [(b"1 (RFC822 {...})", self._raw_message)]

    def store(self, num: str, command: str, flags: str) -> tuple[str, list[bytes]]:
        return "OK", [b"done"]

    def logout(self) -> tuple[str, list[bytes]]:
        return "BYE", [b"logout"]


class _ImapFactory:
    """Stands in for the `imaplib.IMAP4` *class* — a callable that mints a fresh
    `_FakeImap4` "connection" on every call, exactly like `imaplib.IMAP4(host, port)`
    does in production.

    `abort`/`error` are set to the *real* `imaplib.IMAP4.abort`/`.error` exception
    classes, captured before any monkeypatching — `ImapSmtpTransport`'s except clause
    looks them up as `imaplib.IMAP4.abort` at handling time, so whatever object
    `imaplib.IMAP4` is patched to must carry them, or that lookup itself raises.
    """

    abort = imaplib.IMAP4.abort
    error = imaplib.IMAP4.error

    def __init__(
        self,
        *,
        raw_message: bytes = b"",
        fail_first_n: int = 0,
        record_selected: list[str] | None = None,
    ) -> None:
        self._raw_message = raw_message
        self._fail_first_n = fail_first_n
        self._record_selected = record_selected
        self.attempts = 0

    def __call__(self, host: str, port: int, *args: object, **kwargs: object) -> _FakeImap4:
        self.attempts += 1
        n = self.attempts

        def on_select(inst: _FakeImap4) -> None:
            if self._record_selected is not None:
                self._record_selected.append(inst.selected or "")
            if n <= self._fail_first_n:
                raise _ImapFactory.abort("simulated: connection reset mid-poll")

        return _FakeImap4(host, port, raw_message=self._raw_message, on_select=on_select)


def _config(**over: object) -> ImapSmtpConfig:
    base: dict[str, object] = {
        "imap_host": "fake",
        "imap_use_tls": False,
        "imap_user": "svc@example.test",
        "imap_password": "x",
    }
    base.update(over)
    return ImapSmtpConfig(**base)  # type: ignore[arg-type]


def test_fetch_unseen_reconnects_after_a_mid_poll_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeImap4.instances = []
    factory = _ImapFactory(raw_message=_raw_message(), fail_first_n=1)

    monkeypatch.setattr(imaplib, "IMAP4", factory)
    transport = ImapSmtpTransport(_config(), max_retries=2)

    result = asyncio.run(transport.fetch_unseen())

    assert factory.attempts == 2  # first attempt failed, a fresh second one recovered
    assert len(result) == 1
    assert len(_FakeImap4.instances) == 2  # two distinct connections, not one reused


def test_fetch_unseen_raises_once_retries_are_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _ImapFactory(fail_first_n=99)  # every attempt fails

    monkeypatch.setattr(imaplib, "IMAP4", factory)
    transport = ImapSmtpTransport(_config(), max_retries=2)

    with pytest.raises(MailTransportConnectionError):
        asyncio.run(transport.fetch_unseen())

    assert factory.attempts == 3  # the initial attempt plus both retries, each a fresh connection


def test_fetch_unseen_searches_unseen_not_all(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeImap4.instances.clear()
    factory = _ImapFactory(raw_message=_raw_message())
    monkeypatch.setattr(imaplib, "IMAP4", factory)
    transport = ImapSmtpTransport(_config())

    asyncio.run(transport.fetch_unseen())

    assert _FakeImap4.instances[-1].search_criteria == ("UNSEEN",)


def test_fetch_unseen_selects_the_configured_folder_never_hardcoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected: list[str] = []
    factory = _ImapFactory(raw_message=_raw_message(), record_selected=selected)

    monkeypatch.setattr(imaplib, "IMAP4", factory)
    transport = ImapSmtpTransport(_config(folder="FormRequests"))

    asyncio.run(transport.fetch_unseen())

    assert selected == ["FormRequests"]


def test_duplicate_message_id_across_two_uids_collapses_to_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _DupImap4(_FakeImap4):
        def search(self, charset: str | None, *criteria: str) -> tuple[str, list[bytes]]:
            return "OK", [b"1 2"]

        def fetch(self, num: str, parts: str) -> tuple[str, list[tuple[bytes, bytes] | None]]:
            return "OK", [(b"x", _raw_message("<same@example.test>"))]

    monkeypatch.setattr(imaplib, "IMAP4", _DupImap4)
    transport = ImapSmtpTransport(_config())

    result = asyncio.run(transport.fetch_unseen())

    assert len(result) == 1


def test_mark_seen_local_ledger_is_authoritative_even_if_server_flagging_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ExplodingImap4(_FakeImap4):
        def select(self, folder: str = "INBOX", readonly: bool = False) -> tuple[str, list[bytes]]:
            raise RuntimeError("server-side flagging is unavailable")

    monkeypatch.setattr(imaplib, "IMAP4", _ExplodingImap4)
    transport = ImapSmtpTransport(_config())

    # Must not raise: best-effort \Seen flagging failing is not a caller-visible error.
    asyncio.run(transport.mark_seen("<a@example.test>"))

    assert "<a@example.test>" in transport._seen_ids


def test_send_never_falls_back_to_port_25(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []

    class _FakeSmtp:
        def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
            calls.append((host, port))

        def starttls(self, context: object = None) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            pass

        def send_message(self, msg: object) -> None:
            pass

        def quit(self) -> tuple[str, bytes]:
            return "221", b"bye"

    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    transport = ImapSmtpTransport(
        _config(
            smtp_host="mail.example.test",
            smtp_port=587,
            smtp_use_tls=True,
            mail_from="svc@example.test",
        )
    )

    asyncio.run(transport.send(OutboundMessage(to="a@b.test", subject="s", body="b")))

    assert calls == [("mail.example.test", 587)]
    assert all(port != 25 for _host, port in calls)


def test_send_reconnects_after_a_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    attempt_count = {"n": 0}

    class _FlakySmtp:
        def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
            attempt_count["n"] += 1
            self._attempt = attempt_count["n"]

        def starttls(self, context: object = None) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            pass

        def send_message(self, msg: object) -> None:
            if self._attempt == 1:
                raise smtplib.SMTPServerDisconnected("simulated: connection dropped mid-send")

        def quit(self) -> tuple[str, bytes]:
            return "221", b"bye"

    monkeypatch.setattr(smtplib, "SMTP", _FlakySmtp)
    transport = ImapSmtpTransport(
        _config(smtp_host="mail.example.test", smtp_port=587, mail_from="svc@example.test"),
        max_retries=2,
    )

    asyncio.run(transport.send(OutboundMessage(to="a@b.test", subject="s", body="b")))

    assert attempt_count["n"] == 2


def test_sequence_numbers_handles_empty_and_malformed_search_results() -> None:
    assert _sequence_numbers([]) == []
    assert _sequence_numbers([None]) == []  # type: ignore[list-item]
    assert _sequence_numbers([b""]) == []
    assert _sequence_numbers([b"1 2 3"]) == ["1", "2", "3"]


def test_fetch_unseen_treats_a_non_ok_select_as_a_reconnectable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BadSelectImap4(_FakeImap4):
        def select(self, folder: str = "INBOX", readonly: bool = False) -> tuple[str, list[bytes]]:
            self.selected = folder
            return "NO", [b"folder does not exist"]

    monkeypatch.setattr(imaplib, "IMAP4", _BadSelectImap4)
    transport = ImapSmtpTransport(_config(), max_retries=0)

    with pytest.raises(MailTransportConnectionError):
        asyncio.run(transport.fetch_unseen())


def test_fetch_unseen_treats_a_non_ok_search_as_a_reconnectable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BadSearchImap4(_FakeImap4):
        def search(self, charset: str | None, *criteria: str) -> tuple[str, list[bytes]]:
            return "NO", [b""]

    monkeypatch.setattr(imaplib, "IMAP4", _BadSearchImap4)
    transport = ImapSmtpTransport(_config(), max_retries=0)

    with pytest.raises(MailTransportConnectionError):
        asyncio.run(transport.fetch_unseen())


def test_fetch_unseen_skips_a_uid_whose_fetch_itself_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class _PartialFailureImap4(_FakeImap4):
        def search(self, charset: str | None, *criteria: str) -> tuple[str, list[bytes]]:
            return "OK", [b"1 2"]

        def fetch(self, num: str, parts: str) -> tuple[str, list[tuple[bytes, bytes] | None]]:
            if num == "1":
                return "NO", [None]
            return "OK", [(b"2", _raw_message("<second@example.test>"))]

    monkeypatch.setattr(imaplib, "IMAP4", _PartialFailureImap4)
    transport = ImapSmtpTransport(_config())

    result = asyncio.run(transport.fetch_unseen())

    assert [m.message_id for m in result] == ["<second@example.test>"]


def test_fetch_unseen_excludes_a_message_already_marked_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _SeenAwareImap4(_FakeImap4):
        def __init__(self, host: str, port: int, *a: object, **k: object) -> None:
            super().__init__(host, port, raw_message=_raw_message("<already-seen@example.test>"))

    monkeypatch.setattr(imaplib, "IMAP4", _SeenAwareImap4)
    transport = ImapSmtpTransport(_config())

    asyncio.run(transport.mark_seen("<already-seen@example.test>"))
    result = asyncio.run(transport.fetch_unseen())

    assert result == []


def test_flag_seen_best_effort_returns_quietly_when_search_is_not_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BadSearchImap4(_FakeImap4):
        def search(self, charset: str | None, *criteria: str) -> tuple[str, list[bytes]]:
            return "NO", [b""]

    monkeypatch.setattr(imaplib, "IMAP4", _BadSearchImap4)
    transport = ImapSmtpTransport(_config())

    asyncio.run(transport.mark_seen("<a@example.test>"))  # must not raise


def test_flag_seen_best_effort_flags_every_matching_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    stored: list[tuple[str, str, str]] = []

    class _MatchingImap4(_FakeImap4):
        def search(self, charset: str | None, *criteria: str) -> tuple[str, list[bytes]]:
            return "OK", [b"3 4"]

        def store(self, num: str, command: str, flags: str) -> tuple[str, list[bytes]]:
            stored.append((num, command, flags))
            return "OK", [b"done"]

    monkeypatch.setattr(imaplib, "IMAP4", _MatchingImap4)
    transport = ImapSmtpTransport(_config())

    asyncio.run(transport.mark_seen("<a@example.test>"))

    assert stored == [("3", "+FLAGS", "\\Seen"), ("4", "+FLAGS", "\\Seen")]


def test_smtp_connect_logs_in_when_a_username_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logins: list[tuple[str, str]] = []

    class _FakeSmtp:
        def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
            pass

        def starttls(self, context: object = None) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            logins.append((user, password))

        def send_message(self, msg: object) -> None:
            pass

        def quit(self) -> tuple[str, bytes]:
            return "221", b"bye"

    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    transport = ImapSmtpTransport(
        _config(
            smtp_host="mail.example.test",
            smtp_user="svc@example.test",
            smtp_password="secret",
            mail_from="svc@example.test",
        )
    )

    asyncio.run(transport.send(OutboundMessage(to="a@b.test", subject="s", body="b")))

    assert logins == [("svc@example.test", "secret")]


def test_send_raises_once_smtp_retries_are_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    class _AlwaysDownSmtp:
        def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
            pass

        def starttls(self, context: object = None) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            pass

        def send_message(self, msg: object) -> None:
            raise smtplib.SMTPServerDisconnected("simulated: always down")

        def quit(self) -> tuple[str, bytes]:
            return "221", b"bye"

    monkeypatch.setattr(smtplib, "SMTP", _AlwaysDownSmtp)
    transport = ImapSmtpTransport(
        _config(smtp_host="mail.example.test", mail_from="svc@example.test"), max_retries=1
    )

    with pytest.raises(MailTransportConnectionError):
        asyncio.run(transport.send(OutboundMessage(to="a@b.test", subject="s", body="b")))


def test_imap_connect_uses_imap4_ssl_when_tls_is_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    ssl_calls: list[tuple[str, int]] = []

    class _FakeImap4Ssl(_FakeImap4):
        def __init__(self, host: str, port: int, *a: object, **k: object) -> None:
            ssl_calls.append((host, port))
            super().__init__(host, port, raw_message=_raw_message())

    monkeypatch.setattr(imaplib, "IMAP4_SSL", _FakeImap4Ssl)
    transport = ImapSmtpTransport(_config(imap_use_tls=True, imap_host="imap.example.test"))

    result = asyncio.run(transport.fetch_unseen())

    assert ssl_calls == [("imap.example.test", 993)]
    assert len(result) == 1
