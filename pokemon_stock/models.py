"""Domain types shared across the monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Availability(str, Enum):
    """Normalized availability for a single fulfillment channel."""

    IN_STOCK = "IN_STOCK"
    LIMITED = "LIMITED"
    PREORDER = "PREORDER"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"

    @property
    def is_buyable(self) -> bool:
        return self in (Availability.IN_STOCK, Availability.LIMITED, Availability.PREORDER)


# RedSky returns a fairly wide vocabulary; map every value we have seen onto
# our four meaningful states. Unknown strings stay UNKNOWN so they show up in
# logs instead of being silently treated as a restock.
_REDSKY_STATUS = {
    "IN_STOCK": Availability.IN_STOCK,
    "AVAILABLE": Availability.IN_STOCK,
    "LIMITED_STOCK": Availability.LIMITED,
    "IN_STOCK_LIMITED": Availability.LIMITED,
    "PRE_ORDER_SELLABLE": Availability.PREORDER,
    "PRE_ORDER_UNSELLABLE": Availability.OUT_OF_STOCK,
    "OUT_OF_STOCK": Availability.OUT_OF_STOCK,
    "NOT_SOLD_IN_STORE": Availability.UNAVAILABLE,
    "UNAVAILABLE": Availability.UNAVAILABLE,
    "NOT_AVAILABLE": Availability.UNAVAILABLE,
}


def parse_availability(raw: str | None) -> Availability:
    if not raw:
        return Availability.UNKNOWN
    return _REDSKY_STATUS.get(raw.strip().upper(), Availability.UNKNOWN)


class Channel(str, Enum):
    """Fulfillment channels we can watch."""

    SHIPPING = "shipping"
    PICKUP = "pickup"


@dataclass(frozen=True)
class StoreStock:
    """Pickup availability at one physical store."""

    store_id: str
    store_name: str
    availability: Availability
    quantity: float | None = None


@dataclass
class ProductStock:
    """A single poll result for one TCIN."""

    tcin: str
    title: str
    url: str
    price: str | None = None
    shipping: Availability = Availability.UNKNOWN
    stores: list[StoreStock] = field(default_factory=list)
    raw_shipping_status: str | None = None

    @property
    def pickup(self) -> Availability:
        """Best pickup availability across all watched stores."""
        best = Availability.UNAVAILABLE if self.stores else Availability.UNKNOWN
        order = [
            Availability.IN_STOCK,
            Availability.LIMITED,
            Availability.PREORDER,
            Availability.OUT_OF_STOCK,
            Availability.UNAVAILABLE,
            Availability.UNKNOWN,
        ]
        for store in self.stores:
            if order.index(store.availability) < order.index(best):
                best = store.availability
        return best

    def availability_for(self, channel: Channel) -> Availability:
        return self.shipping if channel is Channel.SHIPPING else self.pickup

    def buyable_channels(self, channels: list[Channel]) -> list[Channel]:
        return [c for c in channels if self.availability_for(c).is_buyable]

    def is_buyable(self, channels: list[Channel]) -> bool:
        return bool(self.buyable_channels(channels))

    def pickup_stores_in_stock(self) -> list[StoreStock]:
        return [s for s in self.stores if s.availability.is_buyable]

    def summary(self, channels: list[Channel]) -> str:
        parts = [f"배송 {self.shipping.value}"]
        if Channel.PICKUP in channels:
            hits = self.pickup_stores_in_stock()
            if hits:
                names = ", ".join(f"{s.store_name}({s.store_id})" for s in hits)
                parts.append(f"픽업 {self.pickup.value} @ {names}")
            else:
                parts.append(f"픽업 {self.pickup.value}")
        return " | ".join(parts)
