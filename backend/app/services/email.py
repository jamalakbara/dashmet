"""SMTP email sending.

Kept deliberately small: stdlib `smtplib` only (no extra dependency). The one
public helper — `send_invite_email` — is called from the org invite endpoint
*after* the membership row is committed, so email delivery never gates the
invite's existence (P-8: the durable trace is the DB row, not the email).

Delivery contract:
- SMTP not configured (`SMTP_HOST` empty) → log the accept link, return False.
  This is the dev fallback; nothing is emailed but the invite is unaffected.
- SMTP configured and the server rejects the message → raise `EmailError`, so a
  real delivery failure is a distinguishable error, never a silent success.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings

logger = logging.getLogger(__name__)


class EmailError(Exception):
    """A configured SMTP server rejected or failed to accept a message."""


def _send(to: str, subject: str, text_body: str, html_body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    from_addr = settings.SMTP_FROM or settings.SMTP_USER
    msg["From"] = formataddr((settings.SMTP_FROM_NAME, from_addr))
    msg["To"] = to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        if settings.SMTP_USE_SSL:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, context=ctx, timeout=15
            ) as server:
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=15
            ) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls(context=ssl.create_default_context())
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(str(e)) from e


def send_invite_email(
    to: str, token: str, org_name: str, inviter_name: str
) -> bool:
    """Send an org invite email.

    Returns True when the email was handed to a configured SMTP server, False
    when SMTP is not configured (the accept link is logged instead — dev only).
    Raises `EmailError` only when a configured server fails.
    """
    accept_url = f"{settings.FRONTEND_URL}/accept-invite?token={token}"

    if not settings.SMTP_HOST:
        logger.info("[DEV] SMTP not configured — invite link for %s: %s", to, accept_url)
        return False

    subject = f"{inviter_name} invited you to {org_name} on DashMet"
    text_body = (
        f"{inviter_name} invited you to join {org_name} on DashMet.\n\n"
        f"Accept your invitation:\n{accept_url}\n\n"
        f"This link expires in 7 days. If you weren't expecting this, ignore "
        f"this email."
    )
    html_body = f"""\
<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:480px;margin:0 auto;color:#1f2937">
  <h2 style="margin:0 0 8px">You're invited to {org_name}</h2>
  <p style="margin:0 0 16px;color:#4b5563">
    {inviter_name} invited you to join <strong>{org_name}</strong> on DashMet.
  </p>
  <p style="margin:0 0 24px">
    <a href="{accept_url}"
       style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:10px 20px;border-radius:8px;font-weight:600">
      Accept invitation
    </a>
  </p>
  <p style="margin:0 0 4px;color:#6b7280;font-size:13px">
    Or paste this link into your browser:
  </p>
  <p style="margin:0 0 24px;color:#6b7280;font-size:13px;word-break:break-all">{accept_url}</p>
  <p style="margin:0;color:#9ca3af;font-size:12px">
    This link expires in 7 days. If you weren't expecting this, you can ignore this email.
  </p>
</div>"""

    _send(to, subject, text_body, html_body)
    logger.info("Invite email sent to %s", to)
    return True
