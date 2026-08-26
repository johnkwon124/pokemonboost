"""Resy.

Two endpoints are involved. ``/4/venue/calendar`` reports, for a whole date
range in one request, which days have any inventory at all — a cheap filter
that keeps a three-month watch down to a handful of real queries. ``/4/find``
then returns the individual seatings for a day that looks promising.
"""

from __future__ import annotations

import datetime as dt
import os

from ..models import Slot
from .base import Provider, ProviderError

CALENDAR_URL = "https://api.resy.com/4/venue/calendar"
FIND_URL = "https://api.resy.com/4/find"


class ResyProvider(Provider):
    name = "resy"

    def __init__(self, config) -> None:
        super().__init__(config)
        api_key = os.environ.get("RESY_API_KEY") or self.venue.options.get("api_key")
        if not api_key:
            raise ProviderError(
                "resy: RESY_API_KEY is not set. Open resy.com in a browser, look at any "
                "XHR to api.resy.com in devtools, and copy the key out of the "
                'Authorization: ResyAPI api_key="..." header.'
            )
        self.session.headers.update(
            {
                "Authorization": f'ResyAPI api_key="{api_key}"',
                "Origin": "https://resy.com",
                "Referer": "https://resy.com/",
                "X-Origin": "https://resy.com",
            }
        )
        token = os.environ.get("RESY_AUTH_TOKEN")
        if token:
            # Some venues only expose inventory to a signed-in account.
            self.session.headers["X-Resy-Auth-Token"] = token
            self.session.headers["X-Resy-Universal-Auth"] = token

    def bookable_dates(self, days: list[dt.date]) -> list[dt.date]:
        if not days:
            return []
        payload = self._get(
            CALENDAR_URL,
            params={
                "venue_id": self.venue.venue_id,
                "num_seats": self.config.party_size,
                "start_date": min(days).isoformat(),
                "end_date": max(days).isoformat(),
            },
        )
        if not payload:
            return days
        open_days = set()
        for entry in payload.get("scheduled", []):
            inventory = (entry.get("inventory") or {}).get("reservation")
            if inventory == "available":
                try:
                    open_days.add(dt.date.fromisoformat(entry["date"]))
                except (KeyError, ValueError):
                    continue
        wanted = set(days)
        return sorted(open_days & wanted)

    def slots_for_date(self, day: dt.date) -> list[Slot]:
        payload = self._get(
            FIND_URL,
            params={
                "lat": 0,
                "long": 0,
                "day": day.isoformat(),
                "party_size": self.config.party_size,
                "venue_id": self.venue.venue_id,
            },
        )
        if not payload:
            return []
        venues = (payload.get("results") or {}).get("venues") or []
        slots: list[Slot] = []
        for venue in venues:
            for raw in venue.get("slots") or []:
                start_text = ((raw.get("date") or {}).get("start") or "").strip()
                if not start_text:
                    continue
                try:
                    start = dt.datetime.strptime(start_text, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                if start.date() != day:
                    continue
                config = raw.get("config") or {}
                slots.append(
                    Slot(
                        start=start,
                        party_size=self.config.party_size,
                        table_type=str(config.get("type") or ""),
                        booking_url=self.booking_url(day, start.strftime("%H:%M")),
                    )
                )
        return slots
