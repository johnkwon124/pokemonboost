import datetime as dt

import pytest

from reservation_monitor.config import ConfigError, load_config

VALID = """
enabled: true
restaurant:
  name: Somewhere Good
  provider: resy
  venue_id: "12345"
  timezone: America/Los_Angeles
party_size: 3
date_range:
  start: "2026-10-01"
  end: "2026-12-31"
targets:
  - weekday: friday
    time: "19:00"
    tolerance_minutes: 30
  - weekday: saturday
    time: "16:00"
notify:
  to: someone@example.com
"""


def write(tmp_path, text):
    path = tmp_path / "reservation.yaml"
    path.write_text(text)
    return path


def test_loads_a_valid_config(tmp_path):
    config = load_config(write(tmp_path, VALID))
    assert config.enabled
    assert config.venue.provider == "resy"
    assert config.party_size == 3
    assert config.targets[0].weekday == 4
    assert config.targets[0].at == dt.time(19, 0)
    assert config.targets[1].tolerance_minutes == 0
    assert config.notify.to == ["someone@example.com"]


def test_recipients_accept_a_comma_separated_string(tmp_path):
    config = load_config(write(tmp_path, VALID.replace("someone@example.com", "a@x.com, b@x.com")))
    assert config.notify.to == ["a@x.com", "b@x.com"]


def test_env_overrides_recipients_and_venue(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTIFY_TO", "override@x.com")
    monkeypatch.setenv("VENUE_ID", "99")
    config = load_config(write(tmp_path, VALID))
    assert config.notify.to == ["override@x.com"]
    assert config.venue.venue_id == "99"


def test_past_dates_are_clamped_to_today(tmp_path):
    config = load_config(write(tmp_path, VALID))
    start, end = config.clamp_to_today(dt.date(2026, 11, 15))
    assert start == dt.date(2026, 11, 15)
    assert end == dt.date(2026, 12, 31)


def test_missing_venue_id_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="venue_id"):
        load_config(write(tmp_path, VALID.replace('venue_id: "12345"', 'venue_id: ""')))


def test_unknown_weekday_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="weekday"):
        load_config(write(tmp_path, VALID.replace("weekday: friday", "weekday: funday")))


def test_backwards_date_range_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="date_range.end"):
        load_config(write(tmp_path, VALID.replace('end: "2026-12-31"', 'end: "2026-09-01"')))


def test_missing_config_file_is_reported(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_a_disabled_config_may_still_be_missing_the_venue(tmp_path):
    text = VALID.replace("enabled: true", "enabled: false").replace('venue_id: "12345"', 'venue_id: ""')
    config = load_config(write(tmp_path, text))
    assert not config.enabled
    assert config.venue.venue_id == ""


def test_an_enabled_config_still_demands_the_venue(tmp_path):
    with pytest.raises(ConfigError, match="venue_id"):
        load_config(write(tmp_path, VALID.replace('venue_id: "12345"', 'venue_id: ""')))
