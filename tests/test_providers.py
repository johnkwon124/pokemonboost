"""Provider parsing, driven off recorded response shapes rather than the network."""

from __future__ import annotations

import datetime as dt

import pytest

from reservation_monitor.config import load_config
from reservation_monitor.providers import build_provider

CONFIG = """
restaurant:
  name: Somewhere Good
  provider: {provider}
  venue_id: "12345"
party_size: 3
date_range:
  start: "2026-10-01"
  end: "2026-12-31"
targets:
  - weekday: friday
    time: "19:00"
    tolerance_minutes: 30
notify:
  to: someone@example.com
"""


def make(tmp_path, provider, monkeypatch, responses):
    monkeypatch.setenv("RESY_API_KEY", "test-key")
    monkeypatch.setenv("OPENTABLE_AUTH_TOKEN", "test-token")
    path = tmp_path / "reservation.yaml"
    path.write_text(CONFIG.format(provider=provider))
    instance = build_provider(load_config(path))
    calls: list[str] = []

    def fake_request(method, url, **kwargs):
        calls.append(url)
        return responses.pop(0) if responses else None

    monkeypatch.setattr(instance, "_request", fake_request)
    instance.calls = calls
    return instance


RESY_CALENDAR = {
    "scheduled": [
        {"date": "2026-10-02", "inventory": {"reservation": "available"}},
        {"date": "2026-10-09", "inventory": {"reservation": "sold-out"}},
    ]
}

RESY_FIND = {
    "results": {
        "venues": [
            {
                "slots": [
                    {"date": {"start": "2026-10-02 19:00:00"}, "config": {"type": "Dining Room"}},
                    {"date": {"start": "2026-10-02 21:30:00"}, "config": {"type": "Bar"}},
                    {"date": {"start": "bogus"}, "config": {}},
                ]
            }
        ]
    }
}


def test_resy_calendar_narrows_to_days_with_inventory(tmp_path, monkeypatch):
    provider = make(tmp_path, "resy", monkeypatch, [RESY_CALENDAR])
    days = [dt.date(2026, 10, 2), dt.date(2026, 10, 9), dt.date(2026, 10, 16)]
    assert provider.bookable_dates(days) == [dt.date(2026, 10, 2)]


def test_resy_parses_slots_and_skips_malformed_ones(tmp_path, monkeypatch):
    provider = make(tmp_path, "resy", monkeypatch, [RESY_FIND])
    slots = provider.slots_for_date(dt.date(2026, 10, 2))
    assert [s.start for s in slots] == [
        dt.datetime(2026, 10, 2, 19, 0),
        dt.datetime(2026, 10, 2, 21, 30),
    ]
    assert slots[0].table_type == "Dining Room"
    assert slots[0].party_size == 3
    assert "date=2026-10-02" in slots[0].booking_url or slots[0].booking_url


def test_resy_without_an_api_key_says_so(tmp_path, monkeypatch):
    monkeypatch.delenv("RESY_API_KEY", raising=False)
    path = tmp_path / "reservation.yaml"
    path.write_text(CONFIG.format(provider="resy"))
    with pytest.raises(Exception, match="RESY_API_KEY"):
        build_provider(load_config(path))


SEVENROOMS_RANGE = {
    "data": {
        "availability": {
            "2026-10-02": [
                {
                    "shift_category": "DINNER",
                    "times": [
                        {"time": "6:45 PM", "type": "book"},
                        {"time": "7:00 PM", "type": "book"},
                        {"time": "9:00 PM", "type": "closed"},
                    ],
                }
            ],
            "2026-10-09": [{"times": [{"time": "7:00 PM", "type": "book"}]}],
        }
    }
}


def test_sevenrooms_parses_a_range_and_ignores_unwanted_days(tmp_path, monkeypatch):
    provider = make(tmp_path, "sevenrooms", monkeypatch, [SEVENROOMS_RANGE])
    slots = provider.collect([dt.date(2026, 10, 2)], pause=0)
    assert [s.start for s in slots] == [
        dt.datetime(2026, 10, 2, 18, 45),
        dt.datetime(2026, 10, 2, 19, 0),
    ]


OPENTABLE_PAYLOAD = {
    "data": {
        "availability": [
            {
                "restaurantId": 12345,
                "timeslots": [
                    {"isAvailable": True, "dateTime": "2026-10-02T19:00", "tableAttribute": "STANDARD"},
                    {"isAvailable": False, "dateTime": "2026-10-02T19:15"},
                ],
            }
        ]
    }
}


def test_opentable_keeps_only_available_timeslots(tmp_path, monkeypatch):
    provider = make(tmp_path, "opentable", monkeypatch, [OPENTABLE_PAYLOAD])
    slots = provider.slots_for_date(dt.date(2026, 10, 2))
    assert [s.start for s in slots] == [dt.datetime(2026, 10, 2, 19, 0)]


TOCK_PAYLOAD = {
    "availability": [
        {
            "name": "Dinner",
            "timeslots": [
                {"time": {"hour": 19, "minute": 0}},
                {"time": {"hour": 21, "minute": 0}, "isAvailable": False},
            ],
        }
    ]
}


def test_tock_parses_structured_times(tmp_path, monkeypatch):
    provider = make(tmp_path, "tock", monkeypatch, [TOCK_PAYLOAD])
    slots = provider.slots_for_date(dt.date(2026, 10, 2))
    assert [s.start for s in slots] == [dt.datetime(2026, 10, 2, 19, 0)]


def test_empty_response_yields_no_slots(tmp_path, monkeypatch):
    provider = make(tmp_path, "resy", monkeypatch, [None])
    assert provider.slots_for_date(dt.date(2026, 10, 2)) == []
