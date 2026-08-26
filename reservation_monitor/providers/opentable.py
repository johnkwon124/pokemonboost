"""OpenTable.

OpenTable fronts availability with a GraphQL endpoint that expects a rotating
client token. The token is read from OPENTABLE_AUTH_TOKEN; docs explain where
to copy it from. If the schema shifts under us the run fails loudly rather
than silently reporting "nothing available", which would be worse than an
error e-mail.
"""

from __future__ import annotations

import datetime as dt
import os

from ..models import Slot
from .base import Provider, ProviderError

GQL_URL = "https://www.opentable.com/dapi/fe/gql"

QUERY = """
query RestaurantsAvailability($restaurantIds: [Int]!, $date: String!, $time: String!, $partySize: Int!) {
  availability(
    restaurantIds: $restaurantIds
    date: $date
    time: $time
    partySize: $partySize
  ) {
    restaurantId
    timeslots {
      isAvailable
      dateTime
      slotHash
      tableAttribute
    }
  }
}
"""


class OpenTableProvider(Provider):
    name = "opentable"

    def __init__(self, config) -> None:
        super().__init__(config)
        token = os.environ.get("OPENTABLE_AUTH_TOKEN") or self.venue.options.get("auth_token")
        if not token:
            raise ProviderError(
                "opentable: OPENTABLE_AUTH_TOKEN is not set. Open the restaurant page on "
                "opentable.com, find the POST to /dapi/fe/gql in devtools, and copy the "
                "x-csrf-token (and cookie, as OPENTABLE_COOKIE) from that request."
            )
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "x-csrf-token": token,
                "Origin": "https://www.opentable.com",
                "Referer": self.venue.url or "https://www.opentable.com/",
            }
        )
        cookie = os.environ.get("OPENTABLE_COOKIE")
        if cookie:
            self.session.headers["Cookie"] = cookie

    def slots_for_date(self, day: dt.date) -> list[Slot]:
        anchor = self.venue.options.get("anchor_time", "19:00")
        payload = self._post(
            GQL_URL,
            json_body={
                "operationName": "RestaurantsAvailability",
                "query": QUERY,
                "variables": {
                    "restaurantIds": [int(self.venue.venue_id)],
                    "date": day.isoformat(),
                    "time": anchor,
                    "partySize": self.config.party_size,
                },
            },
        )
        if not payload:
            return []
        if payload.get("errors"):
            raise ProviderError(f"opentable: GraphQL error {payload['errors'][:1]}")
        entries = ((payload.get("data") or {}).get("availability")) or []
        slots: list[Slot] = []
        for entry in entries:
            for raw in entry.get("timeslots") or []:
                if not raw.get("isAvailable"):
                    continue
                start = _parse_datetime(str(raw.get("dateTime") or ""))
                if start is None or start.date() != day:
                    continue
                slots.append(
                    Slot(
                        start=start,
                        party_size=self.config.party_size,
                        table_type=str(raw.get("tableAttribute") or ""),
                        booking_url=self.booking_url(day, start.strftime("%H:%M")),
                    )
                )
        return slots


def _parse_datetime(text: str) -> dt.datetime | None:
    text = text.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(text[: len(fmt) + 2].rstrip("Z"), fmt)
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        return None
