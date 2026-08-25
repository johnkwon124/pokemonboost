"""Posts alerts to a Discord or Slack incoming webhook."""

from __future__ import annotations

import logging

import requests

from pokemon_stock.config import WebhookConfig
from pokemon_stock.notifiers.base import Alert, Notifier

log = logging.getLogger(__name__)


class WebhookNotifier(Notifier):
    name = "webhook"

    def __init__(self, config: WebhookConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()

    def send(self, alert: Alert) -> None:
        text = f"**{alert.title}**\n{alert.body}"
        # Discord expects "content", Slack (and most others) expect "text".
        key = "content" if "discord.com" in self.config.url else "text"
        payload = {key: text}
        try:
            response = self.session.post(self.config.url, json=payload, timeout=15)
            if response.status_code >= 400:
                log.warning("웹훅 전송 실패: HTTP %s %s", response.status_code, response.text[:200])
        except requests.RequestException as exc:
            log.warning("웹훅 전송 실패: %s", exc)
