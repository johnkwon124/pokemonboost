"""Tock (exploretock.com).

Tock's consumer search endpoint takes a business slug and returns the
seatings for one service date.
"""

from __future__ import annotations

import datetime as dt

from ..models import Slot
from .base import Provider

SEARCH_URL = "https://www.exploretock.com/api/consumer/search/availability/business"


class TockProvider(Provider):
    name = "tock"

    def slots_for_date(self, day: dt.date) -> list[Slot]:
        payload = self._post(
            SEARCH_URL,
            json_body={
                "businessId": self.venue.venue_id,
                "date": {"year": day.year, "month": day.month, "day": day.day},
                "partySize": self.config.party_size,
                "productTypes": self.venue.options.get("product_types", ["RESERVATION"]),
            },
            headers={"Content-Type": "application/json", "Origin": "https://www.exploretock.com"},
        )
        if not payload:
            return []
        slots: list[Slot] = []
        for group in payload.get("availability") or payload.get("results") or []:
            for raw in group.get("timeslots") or group.get("times") or []:
                start = _parse_tock_time(raw, day)
                if start is None:
                    continue
                if raw.get("isAvailable") is False:
                    continue
                slots.append(
                    Slot(
                        start=start,
                        party_size=self.config.party_size,
                        table_type=str(group.get("name") or raw.get("experienceName") or ""),
                        booking_url=self.booking_url(day, start.strftime("%H:%M")),
                    )
                )
        return slots


def _parse_tock_time(raw: dict, day: dt.date) -> dt.datetime | None:
    time_field = raw.get("time")
    if isinstance(time_field, dict):
        hour = time_field.get("hour")
        minute = time_field.get("minute", 0)
        if hour is None:
            return None
        return dt.datetime(day.year, day.month, day.day, int(hour), int(minute))
    text = str(raw.get("timeIso") or raw.get("dateTime") or time_field or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        return None
