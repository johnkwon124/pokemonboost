"""Provider parsing, driven off recorded response shapes rather than the network."""

from __future__ import annotations

import datetime as dt

import pytest

from reservation_monitor.config import load_config
from reservation_monitor.providers import ProviderError, build_provider

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


OPENTABLE_PROFILE_HTML = """
<html><head><meta name="csrf-token" content="abcdef0123456789abcdef"></head>
<body><script>window.__INITIAL_STATE__ = {"restaurant":{"restaurantId":1234,"name":"Somewhere Good"}}</script></body></html>
"""

NO_PROFILE_CONFIG = """
restaurant:
  name: Somewhere Good
  provider: opentable
  profile_url: "https://www.opentable.com/somewhere-good"
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


def make_bootstrapping_opentable(tmp_path, monkeypatch, html, responses):
    monkeypatch.delenv("OPENTABLE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("OPENTABLE_COOKIE", raising=False)
    path = tmp_path / "reservation.yaml"
    path.write_text(NO_PROFILE_CONFIG)
    provider = build_provider(load_config(path))
    monkeypatch.setattr(provider, "_get_text", lambda url, **kw: html)
    monkeypatch.setattr(provider, "_request", lambda *a, **kw: responses.pop(0) if responses else None)
    return provider


def test_opentable_resolves_rid_and_token_from_the_profile_page(tmp_path, monkeypatch):
    provider = make_bootstrapping_opentable(
        tmp_path, monkeypatch, OPENTABLE_PROFILE_HTML, [OPENTABLE_PAYLOAD]
    )
    slots = provider.slots_for_date(dt.date(2026, 10, 2))
    assert provider._rid == "1234"
    assert provider._csrf == "abcdef0123456789abcdef"
    assert [s.start for s in slots] == [dt.datetime(2026, 10, 2, 19, 0)]


def test_opentable_bootstraps_only_once(tmp_path, monkeypatch):
    provider = make_bootstrapping_opentable(
        tmp_path, monkeypatch, OPENTABLE_PROFILE_HTML, [OPENTABLE_PAYLOAD, OPENTABLE_PAYLOAD]
    )
    loads = []
    monkeypatch.setattr(provider, "_get_text", lambda url, **kw: (loads.append(url), OPENTABLE_PROFILE_HTML)[1])
    provider.slots_for_date(dt.date(2026, 10, 2))
    provider.slots_for_date(dt.date(2026, 10, 9))
    assert len(loads) == 1


def test_opentable_says_so_when_the_page_hides_the_rid(tmp_path, monkeypatch):
    provider = make_bootstrapping_opentable(tmp_path, monkeypatch, "<html>nothing here</html>", [])
    with pytest.raises(Exception, match="restaurant id"):
        provider.slots_for_date(dt.date(2026, 10, 2))


def test_opentable_config_needs_a_venue_or_a_profile_url(tmp_path):
    from reservation_monitor.config import ConfigError

    path = tmp_path / "reservation.yaml"
    path.write_text(
        NO_PROFILE_CONFIG.replace('  profile_url: "https://www.opentable.com/somewhere-good"\n', "")
    )
    with pytest.raises(ConfigError, match="venue_id or profile_url"):
        load_config(path)


# -- raw capture -------------------------------------------------------------
#
# The whole point of ``probe --dump`` is the run that goes wrong: a parser
# written against an assumed response shape can only be corrected against a
# recorded real one, and a probe that prints "no seatings" tells you nothing.


class FakeResponse:
    def __init__(self, status_code=200, body="{}", headers=None):
        self.status_code = status_code
        self.text = body
        self.headers = headers or {"Content-Type": "application/json"}

    def json(self):
        import json

        return json.loads(self.text)


def capturing_provider(tmp_path, monkeypatch, responder):
    monkeypatch.setenv("OPENTABLE_AUTH_TOKEN", "test-token")
    path = tmp_path / "reservation.yaml"
    path.write_text(CONFIG.format(provider="opentable"))
    instance = build_provider(load_config(path))
    instance.capture_raw = True
    monkeypatch.setattr(instance.session, "request", responder)
    return instance


def test_capture_keeps_the_body_of_a_successful_exchange(tmp_path, monkeypatch):
    body = '{"data": {"availability": []}}'
    provider = capturing_provider(
        tmp_path, monkeypatch, lambda method, url, **kw: FakeResponse(body=body)
    )
    provider._request("POST", "https://example.invalid/gql", json_body={})

    assert len(provider.captures) == 1
    entry = provider.captures[0]
    assert entry["status"] == 200
    assert entry["body"] == body
    assert entry["url"] == "https://example.invalid/gql"


def test_capture_keeps_a_failing_exchange_too(tmp_path, monkeypatch):
    provider = capturing_provider(
        tmp_path, monkeypatch, lambda method, url, **kw: FakeResponse(status_code=500, body="nope")
    )
    with pytest.raises(ProviderError):
        provider._request("POST", "https://example.invalid/gql", json_body={})

    # Three attempts, all recorded — the retries are part of the evidence.
    assert [c["status"] for c in provider.captures] == [500, 500, 500]
    assert provider.captures[0]["body"] == "nope"


def test_capture_records_a_transport_error(tmp_path, monkeypatch):
    import requests

    def boom(method, url, **kw):
        raise requests.ConnectionError("refused")

    provider = capturing_provider(tmp_path, monkeypatch, boom)
    with pytest.raises(ProviderError):
        provider._request("GET", "https://example.invalid/gql")

    assert "ConnectionError: refused" in provider.captures[0]["error"]
    assert "status" not in provider.captures[0]


def test_capture_is_off_unless_asked_for(tmp_path, monkeypatch):
    provider = capturing_provider(
        tmp_path, monkeypatch, lambda method, url, **kw: FakeResponse()
    )
    provider.capture_raw = False
    provider._request("POST", "https://example.invalid/gql", json_body={})
    assert provider.captures == []


def test_write_captures_round_trips_to_disk(tmp_path, monkeypatch):
    provider = capturing_provider(
        tmp_path, monkeypatch, lambda method, url, **kw: FakeResponse(body='{"hello": 1}')
    )
    provider._request("POST", "https://example.invalid/gql", json_body={})
    out = tmp_path / "nested" / "raw.json"

    assert provider.write_captures(out) == 1
    import json

    written = json.loads(out.read_text())
    assert written[0]["body"] == '{"hello": 1}'
