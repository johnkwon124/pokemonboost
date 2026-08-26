"""The SMTP conversation and the shape of the message we hand to it."""

from __future__ import annotations

import pytest

from reservation_monitor.notify import Mailer, NotifyError


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list[str] = []
        self.message = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")
        return False

    def starttls(self):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(f"login:{user}:{password}")

    def send_message(self, message):
        self.calls.append("send")
        self.message = message


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_FROM", "DRY_RUN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SMTP_USER", "jkwon47@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    return FakeSMTP


def test_gmail_defaults_and_the_expected_conversation(smtp):
    Mailer(["jkwon47@gmail.com"]).send("Subject line", "body text")
    sent = smtp.instances[0]
    assert (sent.host, sent.port) == ("smtp.gmail.com", 587)
    assert sent.calls == [
        "starttls",
        "login:jkwon47@gmail.com:app-password",
        "send",
        "quit",
    ]


def test_headers_and_plain_text_body(smtp):
    Mailer(["a@x.com", "b@x.com"]).send("Table open", "come quick")
    message = smtp.instances[0].message
    assert message["Subject"] == "Table open"
    assert message["From"] == "jkwon47@gmail.com"
    assert message["To"] == "a@x.com, b@x.com"
    assert message.get_content_type() == "text/plain"
    assert "come quick" in message.get_content()


def test_html_alternative_is_attached_when_given(smtp):
    Mailer(["a@x.com"]).send("Table open", "text version", "<p>html version</p>")
    message = smtp.instances[0].message
    assert message.get_content_type() == "multipart/alternative"
    parts = {p.get_content_type(): p.get_content() for p in message.iter_parts()}
    assert "text version" in parts["text/plain"]
    assert "html version" in parts["text/html"]


def test_a_custom_host_and_sender_are_honoured(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.fastmail.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_FROM", "alerts@x.com")
    Mailer(["a@x.com"]).send("s", "t")
    sent = smtp.instances[0]
    assert (sent.host, sent.port) == ("smtp.fastmail.com", 465)
    assert sent.message["From"] == "alerts@x.com"


def test_missing_credentials_say_what_to_set(smtp, monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    with pytest.raises(NotifyError, match="SMTP_USER / SMTP_PASSWORD"):
        Mailer(["a@x.com"]).send("s", "t")


def test_dry_run_never_opens_a_connection(smtp, monkeypatch, capsys):
    monkeypatch.setenv("DRY_RUN", "1")
    Mailer(["a@x.com"]).send("Subject", "body")
    assert smtp.instances == []
    assert "Subject" in capsys.readouterr().out


def test_a_refused_connection_is_reported_as_a_notify_error(smtp, monkeypatch):
    def explode(*a, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr("smtplib.SMTP", explode)
    with pytest.raises(NotifyError, match="connection refused"):
        Mailer(["a@x.com"]).send("s", "t")
