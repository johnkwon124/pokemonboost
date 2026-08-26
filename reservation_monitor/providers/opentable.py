"""OpenTable.

Availability comes from OpenTable's GraphQL endpoint, which wants a CSRF token
and session cookies. Rather than ask a human to paste those out of devtools —
they expire, and a four-month unattended watch would quietly go blind when
they did — the provider bootstraps them from the restaurant's own public
profile page on each run. The numeric restaurant id is scraped from the same
page, so the config only needs the profile URL.
"""

from __future__ import annotations

import datetime as dt
import os
import re

from ..models import Slot
from .base import Provider, ProviderError

GQL_URL = "https://www.opentable.com/dapi/fe/gql"

# The profile page embeds its state as JSON in a <script> tag. These are the
# spellings OpenTable has used for the two values we need.
RID_PATTERNS = (
    r'"restaurantId"\s*:\s*(\d{2,9})',
    r'"rid"\s*:\s*(\d{2,9})',
    r'"restaurant_id"\s*:\s*(\d{2,9})',
    r'data-rid="(\d{2,9})"',
)
CSRF_PATTERNS = (
    r'"csrfToken"\s*:\s*"([^"]{16,})"',
    r'window\.__CSRF_TOKEN__\s*=\s*"([^"]{16,})"',
    r'name="csrf-token"\s+content="([^"]{16,})"',
)

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
        self.gql_url: str = str(self.venue.options.get("gql_url") or GQL_URL)
        self._rid: str = str(self.venue.venue_id or "")
        self._csrf: str = os.environ.get("OPENTABLE_AUTH_TOKEN", "")
        self._booted = False
        cookie = os.environ.get("OPENTABLE_COOKIE")
        if cookie:
            self.session.headers["Cookie"] = cookie
        self.session.headers.update(
            {
                "Origin": "https://www.opentable.com",
                "Referer": self.profile_url or "https://www.opentable.com/",
            }
        )

    @property
    def profile_url(self) -> str:
        return self.venue.profile_url or self.venue.url or ""

    # -- credential bootstrap --------------------------------------------

    def _bootstrap(self) -> None:
        """Scrape the restaurant id and a fresh CSRF token off the public page."""
        if self._booted:
            return
        self._booted = True
        if self._rid and self._csrf:
            return
        if not self.profile_url.startswith(("https://", "http://")):
            raise ProviderError(
                "opentable: set restaurant.profile_url to the opentable.com page for the "
                "restaurant (e.g. https://www.opentable.com/house-of-prime-rib), or supply "
                "restaurant.venue_id and OPENTABLE_AUTH_TOKEN explicitly."
            )
        html = self._get_text(self.profile_url)
        if not self._rid:
            self._rid = _first_match(html, RID_PATTERNS) or ""
            if not self._rid:
                raise ProviderError(
                    f"opentable: could not find a restaurant id on {self.profile_url}. "
                    "The page layout may have changed; set restaurant.venue_id by hand."
                )
            print(f"  resolved OpenTable rid={self._rid} from the profile page")
        if not self._csrf:
            self._csrf = _first_match(html, CSRF_PATTERNS) or ""
            if not self._csrf:
                raise ProviderError(
                    "opentable: could not find a CSRF token on the profile page. "
                    "Copy the x-csrf-token header from a /dapi/fe/gql request in devtools "
                    "into the OPENTABLE_AUTH_TOKEN secret as a fallback."
                )

    # -- availability -----------------------------------------------------

    def slots_for_date(self, day: dt.date) -> list[Slot]:
        self._bootstrap()
        anchor = str(self.venue.options.get("anchor_time", "19:00"))
        payload = self._post(
            self.gql_url,
            json_body={
                "operationName": "RestaurantsAvailability",
                "query": QUERY,
                "variables": {
                    "restaurantIds": [int(self._rid)],
                    "date": day.isoformat(),
                    "time": anchor,
                    "partySize": self.config.party_size,
                },
            },
            headers={"Content-Type": "application/json", "x-csrf-token": self._csrf},
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

    def booking_url(self, day: dt.date, clock: str = "") -> str:
        template = self.venue.booking_url_template
        if not template:
            return self.profile_url
        return template.format(
            date=day.isoformat(),
            time=clock,
            party_size=self.config.party_size,
            venue_id=self._rid or self.venue.venue_id,
        )


def _first_match(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        found = re.search(pattern, text)
        if found:
            return found.group(1)
    return None


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
