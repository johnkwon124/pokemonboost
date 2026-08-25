"""Prints alerts to stdout, with a terminal bell so it is noticeable."""

from __future__ import annotations

import sys

from pokemon_stock.notifiers.base import Alert, Notifier


class ConsoleNotifier(Notifier):
    name = "console"

    def send(self, alert: Alert) -> None:
        print("\a" + "=" * 60)
        print(alert.title)
        print(alert.body)
        print("=" * 60)
        sys.stdout.flush()
