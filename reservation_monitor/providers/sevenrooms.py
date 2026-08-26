"""SevenRooms.

Its widget availability endpoint is unauthenticated and accepts a date range,
so a whole month can be fetched in one request.
"""

from __future__ import annotations

import datetime as dt

from ..models import Slot
from .base import Provider

RANGE_URL = "https://www.sevenrooms.com/api-yoa/availability/widget/range"


class SevenRoomsProvider(Provider):
    name = "sevenrooms"

    def bookable_dates(self, days: list[dt.date]) -> list[dt.date]:
        # One request per day is wasteful here; collect() is overridden instead.
        return days

    def collect(self, days: list[dt.date], pause: float = 0.4) -> list[Slot]:
        if not days:
            return []
        wanted = set(days)
        start, end = min(days), max(days)
        slots: list[Slot] = []
        cursor = start
        while cursor <= end:
            span = min(31, (end - cursor).days + 1)
            payload = self._get(
                RANGE_URL,
                params={
                    "venue": self.venue.venue_id,
                    "time_slot": self.venue.options.get("time_slot", "19:00"),
                    "party_size": self.config.party_size,
                    "halo_size_interval": self.venue.options.get("halo_size_interval", 100),
                    "start_date": cursor.strftime("%m-%d-%Y"),
                    "num_days": span,
                    "channel": "SEVENROOMS_WIDGET",
                },
            )
            slots.extend(self._parse_range(payload, wanted))
            cursor += dt.timedelta(days=span)
        return slots

    def _parse_range(self, payload, wanted: set[dt.date]) -> list[Slot]:
        if not payload:
            return []
        availability = ((payload.get("data") or {}).get("availability")) or {}
        slots: list[Slot] = []
        for date_text, entries in availability.items():
            try:
                day = dt.datetime.strptime(date_text, "%Y-%m-%d").date()
            except ValueError:
                continue
            if day not in wanted:
                continue
            for shift in entries or []:
                for raw in shift.get("times") or []:
                    if raw.get("type") not in (None, "book", "request"):
                        continue
                    time_text = str(raw.get("time") or "").strip()
                    parsed = _parse_clock(time_text)
                    if parsed is None:
                        continue
                    slots.append(
                        Slot(
                            start=dt.datetime.combine(day, parsed),
                            party_size=self.config.party_size,
                            table_type=str(raw.get("access_persistent_id") or shift.get("shift_category") or ""),
                            booking_url=self.booking_url(day, parsed.strftime("%H:%M")),
                        )
                    )
        return slots

    def slots_for_date(self, day: dt.date) -> list[Slot]:
        return self.collect([day], pause=0)


def _parse_clock(text: str) -> dt.time | None:
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%H:%M:%S"):
        try:
            return dt.datetime.strptime(text.upper(), fmt).time()
        except ValueError:
            continue
    return None
