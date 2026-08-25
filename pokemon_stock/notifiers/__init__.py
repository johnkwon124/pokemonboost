"""Notifier construction from config."""

from __future__ import annotations

import logging

from pokemon_stock.config import Config
from pokemon_stock.notifiers.base import Alert, Notifier
from pokemon_stock.notifiers.console import ConsoleNotifier
from pokemon_stock.notifiers.desktop import DesktopNotifier
from pokemon_stock.notifiers.email_notifier import EmailNotifier
from pokemon_stock.notifiers.webhook import WebhookNotifier

log = logging.getLogger(__name__)

__all__ = [
    "Alert",
    "Notifier",
    "ConsoleNotifier",
    "DesktopNotifier",
    "EmailNotifier",
    "WebhookNotifier",
    "build_notifiers",
    "dispatch",
]


def build_notifiers(config: Config) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if config.notify.console:
        notifiers.append(ConsoleNotifier())
    if config.notify.desktop:
        notifiers.append(DesktopNotifier())
    if config.notify.webhook.enabled and config.notify.webhook.url:
        notifiers.append(WebhookNotifier(config.notify.webhook))
    email = config.notify.email
    if email.enabled and email.recipients:
        notifiers.append(EmailNotifier(email))
    return notifiers


def dispatch(notifiers: list[Notifier], alert: Alert) -> None:
    """Send one alert everywhere; a broken channel never blocks the others."""
    for notifier in notifiers:
        try:
            notifier.send(alert)
        except Exception as exc:  # noqa: BLE001 - notifiers must never crash the loop
            log.warning("%s 알림 전송 중 오류: %s", notifier.name, exc)
