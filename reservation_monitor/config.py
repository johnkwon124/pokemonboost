"""Loading and validation of config/reservation.yaml."""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import Target
from .release import ReleaseRule

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

DEFAULT_CONFIG_PATH = Path("config/reservation.yaml")


class ConfigError(ValueError):
    """Raised when the YAML config is missing required fields or malformed."""


@dataclass
class VenueConfig:
    name: str
    provider: str
    venue_id: str
    timezone: str = "America/Los_Angeles"
    url: str = ""
    profile_url: str = ""
    booking_url_template: str = ""
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class NotifyConfig:
    to: list[str]
    renotify_after_hours: int = 24
    heartbeat_hour: int | None = 8
    alert_after_consecutive_failures: int = 3
    alert_cooldown_hours: int = 6


@dataclass
class ScanConfig:
    """How much of the date range to cover in a single run.

    Hitting every candidate date on every run would mean thousands of requests
    a day against one endpoint, which is a good way to get throttled. Instead
    each run takes the next slice and the cursor rotates, so the whole range is
    still covered every few runs.
    """

    max_dates_per_run: int = 13
    pause_seconds: float = 0.5


@dataclass
class MonitorConfig:
    enabled: bool
    venue: VenueConfig
    party_size: int
    start_date: dt.date
    end_date: dt.date
    targets: list[Target]
    notify: NotifyConfig
    scan: ScanConfig
    release: ReleaseRule = field(default_factory=ReleaseRule)

    def clamp_to_today(self, today: dt.date) -> tuple[dt.date, dt.date]:
        """Dates in the past are never bookable, so never ask for them."""
        return max(self.start_date, today), self.end_date


def _require(data: dict[str, Any], key: str, where: str) -> Any:
    if key not in data or data[key] in (None, ""):
        raise ConfigError(f"missing required field {where}.{key}")
    return data[key]


def _as_date(value: Any, where: str) -> dt.date:
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.datetime):
        return value.date()
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ConfigError(f"{where} must be YYYY-MM-DD, got {value!r}") from exc


def _as_time(value: Any, where: str) -> dt.time:
    if isinstance(value, dt.time):
        return value
    text = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I%p", "%I:%M%p"):
        try:
            return dt.datetime.strptime(text.upper().replace("PM", " PM").replace("AM", " AM").strip(), fmt).time()
        except ValueError:
            continue
    raise ConfigError(f"{where} must be a 24h time like '19:00', got {value!r}")


def _parse_targets(raw: Any) -> list[Target]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("targets must be a non-empty list")
    targets: list[Target] = []
    for i, item in enumerate(raw):
        where = f"targets[{i}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{where} must be a mapping")
        name = str(_require(item, "weekday", where)).strip().lower()
        if name not in WEEKDAYS:
            raise ConfigError(f"{where}.weekday must be one of {sorted(WEEKDAYS)}, got {name!r}")
        targets.append(
            Target(
                weekday=WEEKDAYS[name],
                at=_as_time(_require(item, "time", where), f"{where}.time"),
                tolerance_minutes=int(item.get("tolerance_minutes", 0)),
                label=str(item.get("label", "")),
            )
        )
    return targets


def _split_recipients(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace(";", ",").split(",")]
    elif isinstance(value, list):
        parts = [str(p).strip() for p in value]
    else:
        raise ConfigError("notify.to must be a string or a list of addresses")
    recipients = [p for p in parts if p]
    if not recipients:
        raise ConfigError("notify.to must contain at least one address")
    return recipients


def load_config(path: str | Path | None = None) -> MonitorConfig:
    """Read the YAML config, applying NOTIFY_TO / RESY_VENUE_ID style overrides."""
    path = Path(path or os.environ.get("RESERVATION_CONFIG") or DEFAULT_CONFIG_PATH)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a YAML mapping")

    enabled = bool(data.get("enabled", True))

    raw_venue = data.get("restaurant") or data.get("venue") or {}
    if not isinstance(raw_venue, dict):
        raise ConfigError("restaurant must be a mapping")
    # A half-finished config is allowed to load as long as it is switched off,
    # so the scheduled job can exit quietly instead of failing every ten
    # minutes while the venue is still being looked up.
    venue_id = os.environ.get("VENUE_ID") or raw_venue.get("venue_id") or ""
    profile_url = str(raw_venue.get("profile_url") or "")
    # A profile_url lets the provider resolve the venue id itself, so only one
    # of the two has to be present.
    if enabled and not venue_id and not profile_url:
        raise ConfigError("restaurant needs either venue_id or profile_url")
    venue = VenueConfig(
        name=str(_require(raw_venue, "name", "restaurant")),
        provider=str(_require(raw_venue, "provider", "restaurant")).strip().lower(),
        venue_id=str(venue_id),
        timezone=str(raw_venue.get("timezone", "America/Los_Angeles")),
        url=str(raw_venue.get("url", "")),
        profile_url=profile_url,
        booking_url_template=str(raw_venue.get("booking_url_template", "")),
        options=dict(raw_venue.get("options") or {}),
    )

    raw_range = data.get("date_range") or {}
    if not isinstance(raw_range, dict):
        raise ConfigError("date_range must be a mapping")
    start = _as_date(_require(raw_range, "start", "date_range"), "date_range.start")
    end = _as_date(_require(raw_range, "end", "date_range"), "date_range.end")
    if end < start:
        raise ConfigError("date_range.end must not be before date_range.start")

    raw_notify = data.get("notify") or {}
    if not isinstance(raw_notify, dict):
        raise ConfigError("notify must be a mapping")
    heartbeat = raw_notify.get("heartbeat_hour", 8)
    notify = NotifyConfig(
        to=_split_recipients(os.environ.get("NOTIFY_TO") or _require(raw_notify, "to", "notify")),
        renotify_after_hours=int(raw_notify.get("renotify_after_hours", 24)),
        heartbeat_hour=None if heartbeat in (None, False, "") else int(heartbeat),
        alert_after_consecutive_failures=int(raw_notify.get("alert_after_consecutive_failures", 3)),
        alert_cooldown_hours=int(raw_notify.get("alert_cooldown_hours", 6)),
    )

    raw_scan = data.get("scan") or {}
    if not isinstance(raw_scan, dict):
        raise ConfigError("scan must be a mapping")
    scan = ScanConfig(
        max_dates_per_run=int(raw_scan.get("max_dates_per_run", 13) or 0),
        pause_seconds=float(raw_scan.get("pause_seconds", 0.5)),
    )
    if scan.max_dates_per_run < 0:
        raise ConfigError("scan.max_dates_per_run must not be negative")

    raw_release = data.get("release") or {}
    if not isinstance(raw_release, dict):
        raise ConfigError("release must be a mapping")
    release = ReleaseRule(
        lead_days=int(raw_release.get("lead_days", 365)),
        open_time=_as_time(raw_release.get("open_time", "09:00"), "release.open_time"),
        alarm_minutes=int(raw_release.get("alarm_minutes", 15)),
        assumed=bool(raw_release.get("assumed", True)),
    )
    if release.lead_days < 0:
        raise ConfigError("release.lead_days must not be negative")

    party_size = int(_require(data, "party_size", "<root>"))
    if party_size < 1:
        raise ConfigError("party_size must be at least 1")

    return MonitorConfig(
        enabled=enabled,
        venue=venue,
        party_size=party_size,
        start_date=start,
        end_date=end,
        targets=_parse_targets(data.get("targets")),
        notify=notify,
        scan=scan,
        release=release,
    )
