"""ImapSmtpConfig — credentials injected at runtime, never baked in; SMTP always
defaults to 587, never 25.
"""

from __future__ import annotations

from email_service.transport import ImapSmtpConfig


def test_from_env_reads_every_field_from_the_given_mapping() -> None:
    env = {
        "IMAP_HOST": "imap.example.test",
        "IMAP_PORT": "1993",
        "IMAP_USE_TLS": "false",
        "IMAP_USER": "svc@example.test",
        "IMAP_PASSWORD": "secret",
        "IMAP_FOLDER": "FormRequests",
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "2525",
        "SMTP_USE_TLS": "false",
        "SMTP_USER": "smtp-user@example.test",
        "SMTP_PASSWORD": "smtp-secret",
        "MAIL_FROM": "forms@example.test",
    }

    config = ImapSmtpConfig.from_env(env)

    assert config.imap_host == "imap.example.test"
    assert config.imap_port == 1993
    assert config.imap_use_tls is False
    assert config.imap_user == "svc@example.test"
    assert config.imap_password == "secret"
    assert config.folder == "FormRequests"
    assert config.smtp_host == "smtp.example.test"
    assert config.smtp_port == 2525
    assert config.smtp_use_tls is False
    assert config.smtp_user == "smtp-user@example.test"
    assert config.smtp_password == "smtp-secret"
    assert config.mail_from == "forms@example.test"


def test_from_env_defaults_never_hardcode_port_25_or_a_folder_other_than_inbox() -> None:
    config = ImapSmtpConfig.from_env({"IMAP_USER": "svc@example.test"})

    assert config.smtp_port == 587  # GCP blocks 25 permanently — never the default
    assert config.folder == "INBOX"
    assert config.imap_use_tls is True  # secure by default for a real deployment


def test_from_env_smtp_credentials_fall_back_to_imap_credentials_when_unset() -> None:
    config = ImapSmtpConfig.from_env({"IMAP_USER": "svc@example.test", "IMAP_PASSWORD": "secret"})

    assert config.smtp_user == "svc@example.test"
    assert config.smtp_password == "secret"
    assert config.mail_from == "svc@example.test"


def test_from_env_defaults_to_os_environ_when_no_mapping_given() -> None:
    # Just proves the no-argument path does not blow up; values depend on the
    # process environment, which this test does not control.
    config = ImapSmtpConfig.from_env()
    assert isinstance(config.imap_host, str)
