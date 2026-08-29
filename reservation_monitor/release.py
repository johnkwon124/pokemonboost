"""Reminders for the moment a date opens for booking.

Chasing cancellations needs a live connection to the booking platform. Being
at the keyboard when the calendar first opens does not: the release moment is
a function of the target date, so it can be computed months in advance and put
in a calendar that fires on its own.

The lead time is configuration, not a fact this code knows. `about a year` is
what the venue handoff recorded, and the exact rule -- 365 days, or the first
of the month a year out, and at what hour -- is worth one phone call to the
restaurant before trusting a year of reminders to it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from zoneinfo import ZoneInfo

# RFC 5545 wants CRLF line endings and lines folded at 75 octets.
_LINE_LIMIT = 75


@dataclass
class ReleaseRule:
    """How far ahead, and at what local time, a date opens for booking."""

    lead_days: int = 365
    open_time: dt.time = dt.time(9, 0)
    alarm_minutes: int = 15
    #: False once someone has confirmed the rule with the venue.
    assumed: bool = True


@dataclass
class Release:
    """One target date and the instant it becomes bookable."""

    target: dt.date
    opens_at: dt.datetime  # timezone-aware, in the venue's zone

    @property
    def is_past(self) -> bool:
        return self.opens_at < dt.datetime.now(self.opens_at.tzinfo)


def release_moment(target: dt.date, rule: ReleaseRule, tz: str) -> dt.datetime:
    """When `target` opens for booking, in the venue's local time."""
    day = target - dt.timedelta(days=rule.lead_days)
    return dt.datetime.combine(day, rule.open_time).replace(tzinfo=ZoneInfo(tz))


def plan(
    targets: list[dt.date], rule: ReleaseRule, tz: str, now: dt.datetime | None = None
) -> tuple[list[Release], list[Release]]:
    """Split target dates into those still to open and those already open.

    The second list is the point of returning a pair. A window whose releases
    have all passed produces no reminders at all, and a caller that only sees
    an empty calendar cannot tell that from having nothing configured.
    """
    zone = ZoneInfo(tz)
    now = now.astimezone(zone) if now else dt.datetime.now(zone)
    upcoming: list[Release] = []
    passed: list[Release] = []
    for target in sorted(targets):
        release = Release(target=target, opens_at=release_moment(target, rule, tz))
        (passed if release.opens_at < now else upcoming).append(release)
    return upcoming, passed


# -- iCalendar ------------------------------------------------------------


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold to 75 octets, splitting on octets rather than characters."""
    raw = line.encode("utf-8")
    if len(raw) <= _LINE_LIMIT:
        return line
    chunks, start = [], 0
    while start < len(raw):
        end = min(start + (_LINE_LIMIT if not chunks else _LINE_LIMIT - 1), len(raw))
        # Never split a multi-byte character across a fold.
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(raw[start:end].decode("utf-8"))
        start = end
    return "\r\n ".join(chunks)


def _utc(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _uid(venue: str, target: dt.date) -> str:
    digest = hashlib.sha1(f"{venue}|{target.isoformat()}".encode()).hexdigest()[:16]
    return f"{digest}@reservation-monitor"


def build_ics(
    releases: list[Release],
    *,
    venue_name: str,
    party_size: int,
    booking_url: str = "",
    rule: ReleaseRule,
    duration_minutes: int = 15,
    now: dt.datetime | None = None,
) -> str:
    """One VEVENT per release, each with an alarm shortly before it opens.

    UIDs are derived from the venue and target date, so re-importing a
    regenerated file updates the existing events instead of duplicating them.
    """
    stamp = _utc(now or dt.datetime.now(dt.timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//reservation-monitor//release reminders//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(venue_name)} booking opens",
    ]
    caveat = (
        "Lead time is assumed, not confirmed with the restaurant — verify it "
        "before relying on these."
        if rule.assumed
        else "Lead time confirmed with the restaurant."
    )
    for release in releases:
        end = release.opens_at + dt.timedelta(minutes=duration_minutes)
        summary = (
            f"Book {venue_name} — {release.target:%a %d %b %Y} (party of {party_size})"
        )
        description = "\n".join(
            [
                f"Reservations for {release.target:%A %d %B %Y} open now.",
                f"Party of {party_size}.",
                f"Assuming a {rule.lead_days}-day lead time. {caveat}",
            ]
        )
        lines += [
            "BEGIN:VEVENT",
            f"UID:{_uid(venue_name, release.target)}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_utc(release.opens_at)}",
            f"DTEND:{_utc(end)}",
            f"SUMMARY:{_escape(summary)}",
            f"DESCRIPTION:{_escape(description)}",
        ]
        if booking_url:
            lines.append(f"URL:{_escape(booking_url)}")
        if rule.alarm_minutes > 0:
            lines += [
                "BEGIN:VALARM",
                f"TRIGGER:-PT{rule.alarm_minutes}M",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{_escape(summary)}",
                "END:VALARM",
            ]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
