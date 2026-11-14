"""Outgoing e-mail over SMTP (standard library). Nothing is sent unless SMTP_HOST and SMTP_FROM are set."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from ..config import Settings

log = logging.getLogger("swara.mail")


class MailError(RuntimeError):
    pass


def is_configured(settings: Settings) -> bool:
    return settings.smtp_configured


def build(settings: Settings, to: str, subject: str, text: str, html: str | None = None) -> EmailMessage:
    for field in (to, subject):
        if "\n" in field or "\r" in field:  # header injection
            raise MailError("Line breaks are not allowed in addresses or subjects.")
    msg = EmailMessage()
    name, addr = parseaddr(settings.smtp_from)
    msg["From"] = formataddr((name or "SWARA AI", addr))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def send(settings: Settings, to: str, subject: str, text: str, html: str | None = None) -> None:
    """Blocking. Raises MailError (without any credential in the message) when delivery fails."""
    if not is_configured(settings):
        raise MailError("E-mail is not configured on this server.")
    msg = build(settings, to, subject, text, html)
    ctx = ssl.create_default_context()
    try:
        if settings.smtp_security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15, context=ctx)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        with server:
            server.ehlo()
            if settings.smtp_security == "starttls":
                server.starttls(context=ctx)
                server.ehlo()
            if settings.smtp_user:
                pw = settings.smtp_password.get_secret_value() if settings.smtp_password else ""
                server.login(settings.smtp_user, pw)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("smtp delivery failed: %s", type(exc).__name__)
        raise MailError("The mail server did not accept the message.") from exc


def link_mail(settings: Settings, kind: str, to: str, name: str, link: str, hours: int) -> tuple[str, str, str]:
    """(subject, text, html) for a verification or reset e-mail."""
    if kind == "verify":
        subject, lead, button = "Confirm your SWARA AI e-mail address", "Confirm your e-mail address to finish creating your account.", "Confirm e-mail"
    else:
        subject, lead, button = "Reset your SWARA AI password", "Someone asked to reset the password for this account. If that was you, use the link below.", "Choose a new password"
    ignore = "If you did not ask for this, you can ignore this message; nothing changes until the link is used."
    text = f"Hello {name},\n\n{lead}\n\n{link}\n\nThe link works once and expires in {hours} hours.\n{ignore}\n\nSWARA AI"
    html = (
        f"<p>Hello {_esc(name)},</p><p>{lead}</p>"
        f'<p><a href="{_esc(link)}" style="background:#D6B574;color:#242424;padding:10px 16px;border-radius:6px;text-decoration:none">{button}</a></p>'
        f"<p>Or paste this address into your browser:<br>{_esc(link)}</p>"
        f"<p>The link works once and expires in {hours} hours. {ignore}</p><p>SWARA AI</p>"
    )
    return subject, text, html


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
