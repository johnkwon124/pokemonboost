"""Full-stack run against a local HTTP server standing in for OpenTable.

Everything except OpenTable's own servers is real here: the requests session,
the profile-page scraping, the GraphQL POST, slot parsing, target matching,
de-duplication and the composed e-mail. It is the closest thing to a live
check that can run without network access.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from reservation_monitor import cli

PROFILE_HTML = """<!doctype html>
<html><head>
<meta name="csrf-token" content="live-token-0123456789abcdef">
</head><body>
<script>window.__INITIAL_STATE__ = {"restaurant":{"restaurantId":7420,"name":"House of Prime Rib"}};</script>
</body></html>"""

# What the fake OpenTable offers: one Friday 7pm, one Saturday 4:15pm (a near
# match), one Friday 9:30pm (too late), and a Sunday that is fully booked.
INVENTORY = {
    "2026-10-02": [("19:00", True), ("21:30", True)],
    "2026-10-03": [("16:15", True), ("18:00", True)],
    "2026-10-04": [("16:00", False)],
}


class FakeOpenTable(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = PROFILE_HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.seen_tokens.append(self.headers.get("x-csrf-token"))
        variables = request["variables"]
        self.server.seen_requests.append(variables)
        day = variables["date"]
        timeslots = [
            {
                "isAvailable": available,
                "dateTime": f"{day}T{clock}",
                "tableAttribute": "STANDARD",
            }
            for clock, available in INVENTORY.get(day, [])
        ]
        body = json.dumps(
            {"data": {"availability": [{"restaurantId": 7420, "timeslots": timeslots}]}}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def fake_opentable():
    server = HTTPServer(("127.0.0.1", 0), FakeOpenTable)
    server.seen_requests = []
    server.seen_tokens = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


CONFIG = """
enabled: true
restaurant:
  name: House of Prime Rib
  provider: opentable
  profile_url: "{base}/house-of-prime-rib"
  timezone: America/Los_Angeles
  booking_url_template: "https://www.opentable.com/restref/client/?rid={{venue_id}}&datetime={{date}}T{{time}}&covers={{party_size}}"
  options:
    gql_url: "{base}/dapi/fe/gql"
party_size: 3
date_range:
  start: "2026-10-01"
  end: "2026-10-05"
targets:
  - weekday: friday
    time: "19:00"
    tolerance_minutes: 30
  - weekday: saturday
    time: "16:00"
    tolerance_minutes: 30
  - weekday: sunday
    time: "16:00"
    tolerance_minutes: 30
scan:
  max_dates_per_run: 0
  pause_seconds: 0
notify:
  to: jkwon47@gmail.com
  heartbeat_hour: null
"""


@pytest.fixture
def run_check(fake_opentable, tmp_path, monkeypatch):
    base = f"http://127.0.0.1:{fake_opentable.server_port}"
    config_path = tmp_path / "reservation.yaml"
    config_path.write_text(CONFIG.format(base=base))
    state_path = tmp_path / "state.json"

    sent: list[tuple[str, str, str | None]] = []
    monkeypatch.setattr(cli.Mailer, "send", lambda self, s, t, h=None: sent.append((s, t, h)))
    monkeypatch.setattr(cli, "_now", lambda config: dt.datetime(2026, 9, 1, 12, 0))

    def run():
        args = cli.build_parser().parse_args(
            ["--config", str(config_path), "check", "--state", str(state_path)]
        )
        return cli.cmd_check(args)

    return run, sent, fake_opentable


def test_full_run_finds_the_right_tables(run_check):
    run, sent, server = run_check
    assert run() == 0

    # Only Fri/Sat/Sun in range were queried, each for a party of three.
    assert sorted(v["date"] for v in server.seen_requests) == [
        "2026-10-02", "2026-10-03", "2026-10-04",
    ]
    assert {v["partySize"] for v in server.seen_requests} == {3}
    # The restaurant id and CSRF token were scraped, not configured.
    assert {v["restaurantIds"][0] for v in server.seen_requests} == {7420}
    assert set(server.seen_tokens) == {"live-token-0123456789abcdef"}

    assert len(sent) == 1
    subject, text, html = sent[0]
    assert "House of Prime Rib" in subject
    bullets = [line.strip() for line in text.splitlines() if line.strip().startswith("•")]
    assert bullets == [
        "• Fri Oct 2, 7:00 PM — STANDARD",          # exact hit
        "• Sat Oct 3, 4:15 PM (+15 min vs target) — STANDARD",  # inside tolerance
    ]
    # 9:30pm Friday, 6pm Saturday and the sold-out Sunday are all left out.
    assert "9:30 PM" not in text and "6:00 PM" not in text and "Oct 4" not in text
    assert "rid=7420" in text
    assert html and html.count("<li") == 2


def test_a_second_run_stays_quiet(run_check):
    run, sent, _ = run_check
    run()
    assert run() == 0
    assert len(sent) == 1


def test_a_dead_endpoint_surfaces_as_a_failure(run_check, monkeypatch):
    run, sent, server = run_check
    server.shutdown()
    server.server_close()
    assert run() == 1
    assert sent == []
