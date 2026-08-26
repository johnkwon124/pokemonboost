"""Core value objects shared by providers, matching and notification."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class Slot:
    """A single bookable seating advertised by a booking platform.

    ``start`` is naive and always expressed in the venue's local timezone,
    because that is what every booking API returns and what the user reads
    off the restaurant's page.
    """

    start: dt.datetime
    party_size: int
    table_type: str = ""
    booking_url: str = ""

    @property
    def day(self) -> dt.date:
        return self.start.date()

    @property
    def clock(self) -> str:
        return self.start.strftime("%-I:%M %p")

    def key(self) -> str:
        """Stable identity used for de-duplicating notifications."""
        return f"{self.start.isoformat(timespec='minutes')}|{self.party_size}|{self.table_type}"


@dataclass(frozen=True)
class Target:
    """One of the user's desired reservation windows, e.g. Friday 7:00 pm."""

    weekday: int  # Monday == 0, matching datetime.date.weekday()
    at: dt.time
    tolerance_minutes: int = 0
    label: str = ""

    def describe(self) -> str:
        name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][self.weekday]
        base = f"{name} {self.at.strftime('%-I:%M %p')}"
        if self.tolerance_minutes:
            return f"{base} (±{self.tolerance_minutes}m)"
        return base


@dataclass(frozen=True)
class Match:
    """A slot that satisfies one of the targets."""

    slot: Slot
    target: Target
    delta_minutes: int

    @property
    def exact(self) -> bool:
        return self.delta_minutes == 0

    def describe(self) -> str:
        when = self.slot.start.strftime("%a %b %-d, %-I:%M %p")
        suffix = "" if self.exact else f" ({self.delta_minutes:+d} min vs target)"
        table = f" — {self.slot.table_type}" if self.slot.table_type else ""
        return f"{when}{suffix}{table}"
