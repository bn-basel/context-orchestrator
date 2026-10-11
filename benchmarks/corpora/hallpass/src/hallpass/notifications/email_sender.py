"""Email via the council SMTP relay (port 25, no auth, IP allow-listed, run
by corporate IT).

A 250 from the relay means "queued", not delivered. Bounces go to a mailbox
nobody reads. TODO: parse bounces and flag dead addresses.

settings.email_backend = "console" prints instead of sending (dev default;
that's how you get your login link locally).
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from hallpass.core.config import get_settings
from hallpass.notifications import templates
from hallpass.notifications.outbox import PermanentSendError, TransientSendError


class SmtpSender:
    def __init__(self, timeout: float = 15.0):
        s = get_settings()
        self.host, self.port, self.sender, self.timeout = s.smtp_host, s.smtp_port, s.email_from, timeout

    def build(self, *, row_id: int, recipient: str, template: str, context: dict) -> EmailMessage:
        subject, body = templates.render_email(template, context)
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = recipient
        msg["Subject"] = subject
        # Stable per outbox row, so when we do send twice Gmail/Outlook usually
        # fold the duplicate away. SMS has no such luck.
        msg["Message-ID"] = make_msgid(idstring=f"hp-outbox-{row_id}")
        msg.set_content(body)
        return msg

    def send(self, *, row_id: int, recipient: str, template: str, context: dict) -> str | None:
        msg = self.build(row_id=row_id, recipient=recipient, template=template, context=context)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                smtp.send_message(msg)
        except smtplib.SMTPRecipientsRefused as exc:
            raise PermanentSendError("recipient refused") from exc
        except smtplib.SMTPResponseException as exc:
            err = PermanentSendError if exc.smtp_code >= 500 else TransientSendError
            raise err(f"smtp {exc.smtp_code}") from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise TransientSendError(f"smtp: {exc}") from exc
        return msg["Message-ID"]


class ConsoleSender:
    def send(self, *, row_id: int, recipient: str, template: str, context: dict) -> str | None:
        subject, body = templates.render_email(template, context)
        print(f"--- email #{row_id} to {recipient}: {subject}\n{body}\n---")
        return None


def default_email_sender():
    return SmtpSender() if get_settings().email_backend == "smtp" else ConsoleSender()
