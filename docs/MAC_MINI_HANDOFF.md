# Handoff: bringing the monitor up on the Mac mini

Everything in this repo was built and tested from an Anthropic cloud container.
That container is in a datacenter, and OpenTable blocks datacenter traffic
outright, so one thing could never be checked from there: **what OpenTable's
live response actually looks like**. The parser is written against a reasonable
reading of their GraphQL schema, not against an observed response.

A Claude session on the Mac mini has what the cloud session lacks — a home IP.
This is the work that session needs to finish.

## What is already settled, so it is not re-investigated

- **The venue.** House of Prime Rib, 1906 Van Ness Ave, San Francisco. Online
  reservations go through OpenTable only.
- **What is being hunted.** Reservations are released about a year ahead, so
  Oct–Dec 2026 is already booked solid. Every table this finds will be a
  cancellation, and those get retaken within minutes.
- **The block is on the IP, not the request.** From GitHub Actions, `robots.txt`
  tarpitted for the full timeout, as did the apex domain and the UK and Canada
  sites; `mobile-api` returned an Akamai *Access Denied*; `api.opentable.com`
  would not connect. `example.com` answered in 0.0s from the same runner. Richer
  headers and a headless browser were both ruled out — do not retry them.
- **The code passes 60 tests**, including a full run against a local HTTP server
  standing in for OpenTable. The logic is not in question; only the assumed
  response shape is.

## The work

1. **Clone and set up.**
   ```bash
   cd ~/Desktop
   git clone -b claude/reservation-monitoring-system-8jxkq8 \
     https://github.com/johnkwon124/pokemonboost.git
   cd pokemonboost
   python3 -m venv .venv && .venv/bin/pip install -r requirements-monitor.txt
   ```

2. **Confirm this machine is treated differently.**
   ```bash
   .venv/bin/python -m reservation_monitor diagnose
   ```
   Both OpenTable lines should say `REACHABLE`. If they say `TARPIT`, stop — the
   home connection is blocked too, and the whole approach needs rethinking.
   Report that rather than working around it.

3. **Look at a real response.** This is the point of the exercise.
   ```bash
   .venv/bin/python -m reservation_monitor probe --days 21
   ```
   It should print seatings. If it errors, or prints nothing where the
   OpenTable website plainly shows times, the GraphQL query or the parser in
   `reservation_monitor/providers/opentable.py` does not match reality. Capture
   the raw payload, fix the parser against it, and add a test to
   `tests/test_providers.py` built from the real shape — the existing OpenTable
   tests are written against an assumed one and should be corrected, not
   preserved.

4. **Ask John for the Gmail app password**, then finish the install:
   ```bash
   ./scripts/install-macos.sh
   ```
   It is safe to re-run and will reuse the virtualenv. Do not invent or guess a
   password, and do not commit it — it belongs in `~/.reservation-monitor/env`,
   `chmod 600`, outside this public repository.

5. **Push whatever changed** to `claude/reservation-monitoring-system-8jxkq8`,
   and tell John what the real response looked like and what had to change.

## Worth knowing

- `docs/RESERVATION_MONITOR.md` has the full design and operational notes.
- Pacing is deliberately gentle for a home connection: 13 of the 39 candidate
  dates per run on a 15-minute timer, covering the quarter every 45 minutes.
  Do not raise it — getting the home IP rate-limited ends the project.
- Silence is meant to mean "no availability", never "the monitor died": there is
  a daily 8am heartbeat e-mail and an alert after three consecutive failures.
  Keep both working.
