"""End-to-end run of `check`, with the network and SMTP stubbed out."""

from __future__ import annotations

import datetime as dt

import pytest

from reservation_monitor import cli
from reservation_monitor.models import Slot

CONFIG = """
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
notify:
  to: someone@example.com
  heartbeat_hour: null
"""


class FakeProvider:
    def __init__(self, slots):
        self._slots = slots
        self.days = None

    def collect(self, days, pause=0.4):
        self.days = days
        return self._slots


@pytest.fixture
def env(tmp_path, monkeypatch):
    config_path = tmp_path / "reservation.yaml"
    config_path.write_text(CONFIG)
    state_path = tmp_path / "state.json"

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(cli.Mailer, "send", lambda self, s, t, h=None: sent.append((s, t)))
    monkeypatch.setattr(cli, "_now", lambda config: dt.datetime(2026, 9, 1, 12, 0))

    def run(slots, exc=None):
        def build(config):
            if exc:
                raise exc
            return FakeProvider(slots)

        monkeypatch.setattr(cli, "build_provider", build)
        args = cli.build_parser().parse_args(
            ["--config", str(config_path), "check", "--state", str(state_path)]
        )
        return cli.cmd_check(args)

    return run, sent, config_path


def fri(clock: str) -> Slot:
    return Slot(start=dt.datetime.fromisoformat(f"2026-10-02T{clock}"), party_size=3)


def test_matching_slot_sends_one_email(env):
    run, sent, _ = env
    assert run([fri("19:00")]) == 0
    assert len(sent) == 1
    subject, body = sent[0]
    assert "Somewhere Good" in subject
    assert "Fri Oct 2, 7:00 PM" in body


def test_non_matching_slots_send_nothing(env):
    run, sent, _ = env
    assert run([fri("21:30")]) == 0
    assert sent == []


def test_the_same_slot_is_not_emailed_twice(env):
    run, sent, _ = env
    run([fri("19:00")])
    run([fri("19:00")])
    assert len(sent) == 1


def test_a_newly_opened_slot_still_gets_through(env):
    run, sent, _ = env
    run([fri("19:00")])
    run([fri("19:00"), fri("18:45")])
    assert len(sent) == 2
    bullets = [line for line in sent[1][1].splitlines() if line.lstrip().startswith("•")]
    assert bullets == ["  • Fri Oct 2, 6:45 PM (-15 min vs target)"]


def test_disabled_config_exits_quietly(env):
    run, sent, config_path = env
    config_path.write_text(CONFIG.replace("enabled: true", "enabled: false"))
    assert run([fri("19:00")]) == 0
    assert sent == []


def test_provider_failure_reports_and_alerts_after_the_threshold(env):
    run, sent, _ = env
    boom = cli.ProviderError("resy: 403 — key expired")
    assert run([], exc=boom) == 1
    assert run([], exc=boom) == 1
    assert sent == []
    assert run([], exc=boom) == 1
    assert len(sent) == 1
    assert "failing" in sent[0][0]
    assert "key expired" in sent[0][1]
