"""Release-date reminders: the arithmetic, and the calendar it produces."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from reservation_monitor.release import (
    Release,
    ReleaseRule,
    build_ics,
    plan,
    release_moment,
)

TZ = "America/Los_Angeles"
RULE = ReleaseRule(lead_days=365, open_time=dt.time(9, 0), alarm_minutes=15)


def test_release_moment_is_the_lead_time_before_the_target():
    opens = release_moment(dt.date(2027, 10, 1), RULE, TZ)
    assert opens.date() == dt.date(2026, 10, 1)
    assert opens.timetz().replace(tzinfo=None) == dt.time(9, 0)


def test_release_moment_is_local_time_on_both_sides_of_a_dst_change():
    """9am local stays 9am local; only the UTC offset moves."""
    summer = release_moment(dt.date(2027, 10, 1), RULE, TZ)
    winter = release_moment(dt.date(2027, 12, 3), RULE, TZ)
    assert summer.hour == winter.hour == 9
    assert summer.utcoffset() == dt.timedelta(hours=-7)  # PDT
    assert winter.utcoffset() == dt.timedelta(hours=-8)  # PST


def test_plan_splits_on_whether_the_release_has_happened():
    now = dt.datetime(2026, 8, 29, 12, 0, tzinfo=ZoneInfo(TZ))
    targets = [dt.date(2026, 10, 2), dt.date(2027, 10, 1)]
    upcoming, passed = plan(targets, RULE, TZ, now=now)

    # 2026-10-02 opened in October 2025; 2027-10-01 opens in October 2026.
    assert [r.target for r in passed] == [dt.date(2026, 10, 2)]
    assert [r.target for r in upcoming] == [dt.date(2027, 10, 1)]


def test_plan_reports_a_window_that_is_entirely_in_the_past():
    """The case that matters: a config whose whole range already opened.

    An empty calendar alone cannot be told apart from nothing configured, so
    the passed list has to come back non-empty.
    """
    now = dt.datetime(2026, 8, 29, 12, 0, tzinfo=ZoneInfo(TZ))
    targets = [dt.date(2026, 10, 2), dt.date(2026, 12, 25)]
    upcoming, passed = plan(targets, RULE, TZ, now=now)

    assert upcoming == []
    assert len(passed) == 2


def test_plan_returns_dates_in_order():
    now = dt.datetime(2026, 8, 29, tzinfo=ZoneInfo(TZ))
    targets = [dt.date(2027, 12, 3), dt.date(2027, 10, 1), dt.date(2027, 11, 5)]
    upcoming, _ = plan(targets, RULE, TZ, now=now)
    assert [r.target for r in upcoming] == sorted(r.target for r in upcoming)


# -- the calendar file ----------------------------------------------------


def make_ics(targets=(dt.date(2027, 10, 1),), rule=RULE, **kw):
    releases = [Release(t, release_moment(t, rule, TZ)) for t in targets]
    return build_ics(
        releases,
        venue_name=kw.pop("venue_name", "House of Prime Rib"),
        party_size=kw.pop("party_size", 3),
        booking_url=kw.pop("booking_url", "https://www.opentable.com/house-of-prime-rib"),
        rule=rule,
        **kw,
    )


def test_ics_uses_crlf_and_folds_to_75_octets():
    ics = make_ics()
    assert ics.endswith("\r\n")
    assert "\n" not in ics.replace("\r\n", "")
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))


def test_ics_brackets_every_event_and_alarm():
    ics = make_ics(targets=[dt.date(2027, 10, 1), dt.date(2027, 10, 2)])
    assert ics.count("BEGIN:VEVENT") == ics.count("END:VEVENT") == 2
    assert ics.count("BEGIN:VALARM") == ics.count("END:VALARM") == 2
    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.rstrip("\r\n").endswith("END:VCALENDAR")


def test_ics_converts_the_local_release_time_to_utc():
    """9am Pacific is 16:00Z in October and 17:00Z in December."""
    assert "DTSTART:20261001T160000Z" in make_ics([dt.date(2027, 10, 1)])
    assert "DTSTART:20261203T170000Z" in make_ics([dt.date(2027, 12, 3)])


def test_ics_uids_are_stable_across_regeneration_and_unique_per_date():
    """Re-importing an updated file should replace events, not duplicate them."""
    import re

    first = re.findall(r"UID:(\S+)", make_ics([dt.date(2027, 10, 1)]))
    again = re.findall(r"UID:(\S+)", make_ics([dt.date(2027, 10, 1)]))
    assert first == again

    two = re.findall(r"UID:(\S+)", make_ics([dt.date(2027, 10, 1), dt.date(2027, 10, 2)]))
    assert len(set(two)) == 2


def test_ics_escapes_commas_and_semicolons_in_the_venue_name():
    ics = make_ics(venue_name="Smith; Jones, Ltd")
    assert r"Smith\; Jones\, Ltd" in ics


def test_ics_says_when_the_lead_time_is_only_assumed():
    assumed = make_ics(rule=ReleaseRule(assumed=True))
    confirmed = make_ics(rule=ReleaseRule(assumed=False))
    assert "not confirmed" in assumed
    assert "not confirmed" not in confirmed


def test_ics_omits_the_alarm_when_it_is_switched_off():
    ics = make_ics(rule=ReleaseRule(alarm_minutes=0))
    assert "BEGIN:VALARM" not in ics


def test_ics_of_no_releases_is_still_a_valid_empty_calendar():
    ics = build_ics([], venue_name="X", party_size=2, rule=RULE)
    assert ics.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" not in ics
