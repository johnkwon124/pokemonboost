"""Notifier interface and the alert payload every channel renders."""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_stock.models import Channel, ProductStock


@dataclass(frozen=True)
class Alert:
    stock: ProductStock
    channels: list[Channel]
    label: str

    @property
    def title(self) -> str:
        return f"🎴 재입고: {self.label}"

    @property
    def body(self) -> str:
        lines = [
            self.label,
            f"상태: {self.stock.summary(self.channels)}",
        ]
        if self.stock.price:
            lines.append(f"가격: {self.stock.price}")
        lines.append(self.stock.url)
        return "\n".join(lines)


class Notifier:
    name = "notifier"

    def send(self, alert: Alert) -> None:  # pragma: no cover - interface
        raise NotImplementedError
