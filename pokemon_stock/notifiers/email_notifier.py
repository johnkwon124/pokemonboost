"""Sends alerts over SMTP (Gmail app passwords work out of the box)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from pokemon_stock.config import EmailConfig
from pokemon_stock.notifiers.base import Alert, Notifier

log = logging.getLogger(__name__)


class EmailNotifier(Notifier):
    name = "email"

    def __init__(self, config: EmailConfig) -> None:
        self.config = config

    def send(self, alert: Alert) -> None:
        message = EmailMessage()
        message["Subject"] = alert.title
        message["From"] = self.config.sender or self.config.username
        message["To"] = ", ".join(self.config.recipients)
        message.set_content(alert.body)

        try:
            with smtplib.SMTP(self.config.host, self.config.port, timeout=20) as smtp:
                if self.config.use_tls:
                    smtp.starttls()
                if self.config.username:
                    smtp.login(self.config.username, self.config.password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            log.warning("이메일 전송 실패: %s", exc)
