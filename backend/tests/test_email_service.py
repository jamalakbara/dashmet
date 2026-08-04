"""Invite email delivery contract (services/email.py).

No SMTP server is contacted: smtplib is patched. These lock the three
behaviours the invite flow depends on — dev fallback, successful send, and a
configured-server failure surfacing as EmailError (never a silent success).
"""
from unittest.mock import MagicMock, patch

import pytest

from app.services import email as email_svc
from app.services.email import EmailError


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
