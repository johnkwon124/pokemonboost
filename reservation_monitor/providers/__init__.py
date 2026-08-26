"""Booking-platform adapters, selected by ``restaurant.provider`` in the config."""

from __future__ import annotations

from ..config import MonitorConfig
from .base import Provider, ProviderError
from .opentable import OpenTableProvider
from .resy import ResyProvider
from .sevenrooms import SevenRoomsProvider
from .tock import TockProvider

REGISTRY: dict[str, type[Provider]] = {
    "resy": ResyProvider,
    "opentable": OpenTableProvider,
    "sevenrooms": SevenRoomsProvider,
    "tock": TockProvider,
}

DEFAULT_BOOKING_URL = {
    "resy": "https://resy.com/cities/sf?date={date}&seats={party_size}",
    "opentable": "https://www.opentable.com/restref/client/?rid={venue_id}&datetime={date}T{time}&covers={party_size}",
    "sevenrooms": "https://www.sevenrooms.com/reservations/{venue_id}?date={date}&party_size={party_size}",
    "tock": "https://www.exploretock.com/{venue_id}/search?date={date}&size={party_size}&time={time}",
}


def build_provider(config: MonitorConfig) -> Provider:
    name = config.venue.provider
    if name not in REGISTRY:
        raise ProviderError(
            f"unknown provider {name!r}; supported: {', '.join(sorted(REGISTRY))}"
        )
    if not config.venue.booking_url_template:
        config.venue.booking_url_template = DEFAULT_BOOKING_URL.get(name, "")
    return REGISTRY[name](config)


__all__ = ["Provider", "ProviderError", "REGISTRY", "build_provider"]
