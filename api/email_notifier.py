"""SMTP adapter for the Notifier port.

Mirrors `EnvTwilioSmsGateway`: every message is recorded locally, and the
network is only touched when SMTP is fully configured. That keeps local dev and
unconfigured deploys working with no special-casing at the call sites.

`send()` never raises. A notification is a side effect of a custody decision,
never a precondition — a mail outage must not fail an override.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

_logger = logging.getLogger(__name__)

_SMTP_TIMEOUT_SECONDS = 10.0


class SmtpEmailNotifier:
    """Sends via SMTP when credentials exist; otherwise records locally.

    Gmail: SMTP_HOST=smtp.gmail.com, SMTP_PORT=587 (STARTTLS), SMTP_USERNAME
    the account address, SMTP_PASSWORD an app password (needs 2FA enabled).
    """

    def __init__(self) -> None:
        self.host = os.getenv("SMTP_HOST")
        self.port = os.getenv("SMTP_PORT")
        self.username = os.getenv("SMTP_USERNAME")
        self.password = os.getenv("SMTP_PASSWORD")
        self.from_address = os.getenv("SMTP_FROM")
        self.sent: list[tuple[str, str, str]] = []

    def _is_configured(self) -> bool:
        return all(
            (self.host, self.port, self.username, self.password, self.from_address)
        )

    def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))
        if not self._is_configured():
            return

        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        try:
            with smtplib.SMTP(
                self.host, int(self.port), timeout=_SMTP_TIMEOUT_SECONDS
            ) as smtp:
                smtp.starttls()
                smtp.login(self.username, self.password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError, ValueError):
            # Log and move on: the override is already committed and matters
            # more than the notification about it.
            _logger.warning("Failed to send notification email to %s", to, exc_info=True)
