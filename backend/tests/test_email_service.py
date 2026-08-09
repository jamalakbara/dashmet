"""Email delivery contract (services/email.py).

No SMTP server is contacted: smtplib is patched. These lock the behaviours all
three flows depend on — dev fallback, successful send with the right link, and a
configured-server failure surfacing as EmailError (never a silent success).
Covers invite, signup verification, and password reset.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.services import email as email_svc
from app.services.email import EmailError


@pytest.fixture(autouse=True)
def _no_resend_by_default(monkeypatch):
    # SMTP/dev-fallback tests assume Resend is off; opt in explicitly per test.
    monkeypatch.setattr(email_svc.settings, "RESEND_API_KEY", "")


def test_dev_fallback_returns_false_when_smtp_unconfigured(monkeypatch, caplog):
    monkeypatch.setattr(email_svc.settings, "SMTP_HOST", "")
    with patch.object(email_svc.smtplib, "SMTP") as smtp:
        with caplog.at_level("INFO"):
            sent = email_svc.send_invite_email(
                "new@example.com", "tok123", "Acme", "Owner"
            )
    assert sent is False
    smtp.assert_not_called()  # nothing was sent
    # The accept link is logged so a dev can still complete the flow.
    assert "accept-invite?token=tok123" in caplog.text


def test_send_uses_starttls_and_login(monkeypatch):
    monkeypatch.setattr(email_svc.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_svc.settings, "SMTP_PORT", 587)
    monkeypatch.setattr(email_svc.settings, "SMTP_USER", "u@example.com")
    monkeypatch.setattr(email_svc.settings, "SMTP_PASSWORD", "secret")
    monkeypatch.setattr(email_svc.settings, "SMTP_USE_SSL", False)
    monkeypatch.setattr(email_svc.settings, "SMTP_USE_TLS", True)
    monkeypatch.setattr(email_svc.settings, "FRONTEND_URL", "https://app.test")

    server = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = server
    with patch.object(email_svc.smtplib, "SMTP", return_value=ctx) as smtp:
        sent = email_svc.send_invite_email(
            "new@example.com", "tok999", "Acme", "Owner"
        )

    assert sent is True
    smtp.assert_called_once()
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("u@example.com", "secret")
    server.send_message.assert_called_once()
    # Sent message carries the accept link for this token.
    msg = server.send_message.call_args.args[0]
    text_part = msg.get_body(preferencelist=("plain",)).get_content()
    assert "https://app.test/accept-invite?token=tok999" in text_part
    assert msg["To"] == "new@example.com"


def test_configured_server_failure_raises_email_error(monkeypatch):
    monkeypatch.setattr(email_svc.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_svc.settings, "SMTP_USE_SSL", False)

    with patch.object(
        email_svc.smtplib, "SMTP", side_effect=OSError("connection refused")
    ):
        with pytest.raises(EmailError):
            email_svc.send_invite_email("new@example.com", "t", "Acme", "Owner")


def test_verification_email_dev_fallback(monkeypatch, caplog):
    monkeypatch.setattr(email_svc.settings, "SMTP_HOST", "")
    with patch.object(email_svc.smtplib, "SMTP") as smtp:
        with caplog.at_level("INFO"):
            sent = email_svc.send_verification_email("new@example.com", "vtok", "Sam")
    assert sent is False
    smtp.assert_not_called()
    assert "verify-email?token=vtok" in caplog.text


def test_verification_email_sends_link(monkeypatch):
    monkeypatch.setattr(email_svc.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_svc.settings, "SMTP_USE_SSL", False)
    monkeypatch.setattr(email_svc.settings, "SMTP_USE_TLS", False)
    monkeypatch.setattr(email_svc.settings, "SMTP_USER", "")
    monkeypatch.setattr(email_svc.settings, "FRONTEND_URL", "https://app.test")

    server = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = server
    with patch.object(email_svc.smtplib, "SMTP", return_value=ctx):
        sent = email_svc.send_verification_email("new@example.com", "vtok9", "Sam")

    assert sent is True
    msg = server.send_message.call_args.args[0]
    text_part = msg.get_body(preferencelist=("plain",)).get_content()
    assert "https://app.test/verify-email?token=vtok9" in text_part


def test_password_reset_email_dev_fallback(monkeypatch, caplog):
    monkeypatch.setattr(email_svc.settings, "SMTP_HOST", "")
    with patch.object(email_svc.smtplib, "SMTP") as smtp:
        with caplog.at_level("INFO"):
            sent = email_svc.send_password_reset_email("new@example.com", "rtok")
    assert sent is False
    smtp.assert_not_called()
    assert "reset-password?token=rtok" in caplog.text


def test_password_reset_email_sends_link(monkeypatch):
    monkeypatch.setattr(email_svc.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_svc.settings, "SMTP_USE_SSL", False)
    monkeypatch.setattr(email_svc.settings, "SMTP_USE_TLS", False)
    monkeypatch.setattr(email_svc.settings, "SMTP_USER", "")
    monkeypatch.setattr(email_svc.settings, "FRONTEND_URL", "https://app.test")

    server = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = server
    with patch.object(email_svc.smtplib, "SMTP", return_value=ctx):
        sent = email_svc.send_password_reset_email("new@example.com", "rtok9")

    assert sent is True
    msg = server.send_message.call_args.args[0]
    text_part = msg.get_body(preferencelist=("plain",)).get_content()
    assert "https://app.test/reset-password?token=rtok9" in text_part


# --- Resend HTTP transport (preferred; used when RESEND_API_KEY is set) ---


def test_resend_is_used_when_api_key_set_and_smtp_never_touched(monkeypatch):
    monkeypatch.setattr(email_svc.settings, "RESEND_API_KEY", "re_test123")
    monkeypatch.setattr(email_svc.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_svc.settings, "RESEND_FROM", "hi@dashmet.ai")
    monkeypatch.setattr(email_svc.settings, "FRONTEND_URL", "https://app.test")

    resp = MagicMock(status_code=200, text='{"id":"abc"}')
    with patch.object(email_svc.smtplib, "SMTP") as smtp, patch.object(
        email_svc.requests, "post", return_value=resp
    ) as post:
        sent = email_svc.send_verification_email("new@example.com", "vtokR", "Sam")

    assert sent is True
    smtp.assert_not_called()  # HTTP transport, not SMTP
    post.assert_called_once()
    url = post.call_args.args[0]
    kwargs = post.call_args.kwargs
    assert url == email_svc.RESEND_ENDPOINT
    assert kwargs["headers"]["Authorization"] == "Bearer re_test123"
    assert kwargs["json"]["to"] == ["new@example.com"]
    assert "https://app.test/verify-email?token=vtokR" in kwargs["json"]["text"]
    assert kwargs["json"]["from"] == "DashMet <hi@dashmet.ai>"


def test_resend_error_status_raises_email_error(monkeypatch):
    monkeypatch.setattr(email_svc.settings, "RESEND_API_KEY", "re_test123")
    resp = MagicMock(status_code=422, text='{"message":"invalid from"}')
    with patch.object(email_svc.requests, "post", return_value=resp):
        with pytest.raises(EmailError):
            email_svc.send_password_reset_email("new@example.com", "rtok")


def test_resend_network_error_raises_email_error(monkeypatch):
    monkeypatch.setattr(email_svc.settings, "RESEND_API_KEY", "re_test123")
    with patch.object(
        email_svc.requests,
        "post",
        side_effect=email_svc.requests.RequestException("boom"),
    ):
        with pytest.raises(EmailError):
            email_svc.send_invite_email("new@example.com", "t", "Acme", "Owner")
