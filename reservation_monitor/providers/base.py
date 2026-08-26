"""Provider interface plus the shared HTTP client every provider uses."""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

import requests

from ..config import MonitorConfig
from ..models import Slot

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class ProviderError(RuntimeError):
    """The booking platform could not be queried (network, auth, or schema)."""


class Provider:
    """Queries one booking platform for a single venue.

    Subclasses implement :meth:`slots_for_date`; the base class walks the
    candidate dates and collects the results.
    """

    name = "base"

    def __init__(self, config: MonitorConfig) -> None:
        self.config = config
        self.venue = config.venue
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    # -- subclass hooks ---------------------------------------------------

    def slots_for_date(self, day: dt.date) -> list[Slot]:
        raise NotImplementedError

    def bookable_dates(self, days: list[dt.date]) -> list[dt.date]:
        """Optional cheap pre-filter. Default: every candidate date."""
        return days

    def booking_url(self, day: dt.date, clock: str = "") -> str:
        template = self.venue.booking_url_template
        if not template:
            return self.venue.url
        return template.format(
            date=day.isoformat(),
            time=clock,
            party_size=self.config.party_size,
            venue_id=self.venue.venue_id,
        )

    # -- driver -----------------------------------------------------------

    def collect(self, days: list[dt.date], pause: float = 0.4) -> list[Slot]:
        found: list[Slot] = []
        for day in self.bookable_dates(days):
            found.extend(self.slots_for_date(day))
            if pause:
                time.sleep(pause)
        return found

    # -- helpers ----------------------------------------------------------

    def _get(self, url: str, *, params: dict | None = None, headers: dict | None = None) -> Any:
        return self._request("GET", url, params=params, headers=headers)

    def _get_text(self, url: str, *, params: dict | None = None, attempts: int = 3) -> str:
        """Fetch a page as text, keeping any cookies the site sets.

        Used to bootstrap credentials off a public page rather than asking a
        human to paste a token that will expire mid-watch.
        """
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = self.session.get(
                    url, params=params, timeout=25, headers={"Accept": "text/html,*/*"}
                )
            except requests.RequestException as exc:
                last = exc
            else:
                if resp.status_code == 200:
                    return resp.text
                last = ProviderError(f"{self.name}: HTTP {resp.status_code} from {url}")
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
        raise ProviderError(f"{self.name}: could not load {url}: {last}")

    def _post(self, url: str, *, json_body: Any = None, headers: dict | None = None) -> Any:
        return self._request("POST", url, json_body=json_body, headers=headers)

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
        headers: dict | None = None,
        attempts: int = 3,
    ) -> Any:
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = self.session.request(
                    method, url, params=params, json=json_body, headers=headers, timeout=25
                )
            except requests.RequestException as exc:
                last = exc
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise ProviderError(
                            f"{self.name}: {url} returned non-JSON ({resp.text[:200]!r})"
                        ) from exc
                if resp.status_code in (401, 403):
                    raise ProviderError(
                        f"{self.name}: {resp.status_code} from {url} — the API key or token "
                        f"is missing or expired. See docs/RESERVATION_MONITOR.md."
                    )
                if resp.status_code == 404:
                    # A venue with nothing on the calendar for that day.
                    return None
                last = ProviderError(f"{self.name}: HTTP {resp.status_code} from {url}")
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
        raise ProviderError(f"{self.name}: request to {url} failed: {last}")
