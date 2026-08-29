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
- ~~**The block is on the IP, not the request.**~~ **Falsified from the Mac
  mini — see "What the home IP actually showed" below.** From GitHub Actions,
  `robots.txt` tarpitted for the full timeout, as did the apex domain and the UK
  and Canada sites; `mobile-api` returned an Akamai *Access Denied*;
  `api.opentable.com` would not connect. `example.com` answered in 0.0s from the
  same runner. That reading — and the rulings against richer headers and a
  headless browser that were derived from it — rested on `robots.txt` being
  caught too. On the home IP it is not.
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
   .venv/bin/python -m reservation_monitor probe --days 21 --dump raw.json
   ```
   It should print seatings. If it errors, or prints nothing where the
   OpenTable website plainly shows times, the GraphQL query or the parser in
   `reservation_monitor/providers/opentable.py` does not match reality. Pass
   `--dump` on the first run whatever happens: it writes every HTTP exchange —
   status, headers, body, and any transport error, retries included — to
   `raw.json` even when the run raises, and that file is the only thing a
   parser fix can be written against. Fix the parser against it and add a test
   to `tests/test_providers.py` built from the real shape — the existing
   OpenTable tests are written against an assumed one and should be corrected,
   not preserved. `raw.json` is untracked; do not commit it.

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

## What the second cloud session found (2026-08-29)

This handoff was picked up by another **cloud** session, not the Mac mini — so
step 2's gate tripped again and steps 3–5 remain unstarted. Worth knowing
before someone re-reads the transcript and thinks the probe has been run:

- The session ran on Ubuntu 24.04 in an Anthropic container behind an
  allowlist egress proxy. `diagnose` did not tarpit; it never left the box.
  All three probes, `example.com` control included, failed as
  `ProxyError … Tunnel connection failed: 403 Forbidden`. A control that fails
  means the run says nothing about OpenTable either way.
- The 60 tests still pass (65 now, with the capture tests below).
- No Gmail app password was requested or stored. It should only ever be
  entered on the Mac mini, into `~/.reservation-monitor/env`. A cloud container
  is ephemeral and is the wrong place for it.
- The parser was **not** touched. Guessing at a second shape to replace the
  first assumed one would only move the guess, and there is still no observed
  response to correct it against.
- What did change: `probe --dump PATH` and the capture plumbing in
  `providers/base.py`, so that the run which finally does reach OpenTable
  leaves the evidence behind instead of just printing `no seatings returned`.

So step 2 is still the first real step, and it has to happen on a machine with
a home IP.

## What the home IP actually showed (2026-08-29, Mac mini)

`diagnose`, run on the Mac mini for the first time:

```
  robots.txt                    REACHABLE  HTTP 200   70356B    0.2s
  venue page                    TARPIT     connected, no response in 15s
  control (example.com)         REACHABLE  HTTP 200     318B    0.1s
```

This is not the clean pass or the clean stop step 2 anticipated, and the split
matters more than either would have:

- **`robots.txt` answers in 0.2s from this IP.** Same host, same header set,
  same TLS handshake, same connecting IP as the venue page. So the block is not
  keyed on the IP. It is keyed on the request — static paths are served, the
  dynamic restaurant page is not.
- **The prohibition on richer headers and a headless browser no longer follows.**
  It was inferred from "a block that catches `robots.txt` must be IP-keyed".
  `robots.txt` is not caught here, so the inference is void. That does not make
  either approach right — it means the question is open again and has to be
  decided on evidence rather than on the old ruling.
- **The monitor cannot run as written.** The provider bootstraps `rid` and the
  CSRF token by scraping the venue page, which is exactly the request that
  tarpits, so `probe` was not attempted — it would die at that first fetch.

Narrowing the cause is the next step, before any fix: whether curl (a different
TLS stack than python-requests) gets the venue page, whether `/dapi/fe/gql`
answers on its own, and what `robots.txt` — now that it is readable — actually
permits on these paths. That last one is a constraint on the answer, not a
detail: if it disallows them, the approach gets reconsidered rather than worked
around.

## The answer to step 3: the real response is a refusal

Narrowing the venue-page tarpit with a second client settled it. Same Mac mini,
same home IP, same Chrome user-agent throughout:

| client         | HTTP | path              | result                  |
|----------------|------|-------------------|-------------------------|
| python-requests| 1.1  | `robots.txt`      | 200, 70356B, 0.2s       |
| curl           | 2    | `robots.txt`      | RST_STREAM, 0.12s       |
| python-requests| 1.1  | venue page        | tarpit, 15s             |
| curl           | 2    | venue page        | RST_STREAM, 0.12s       |
| curl           | 2    | `/dapi/fe/gql`    | 403, 0.2s               |

The same `robots.txt` succeeds for one client and is cut off for the other, and
curl's connection is reset in 0.115s — actively closed, not timed out. So the
refusal is keyed on the client, not the IP and not the path: this is bot
detection (Akamai) varying its rejection mode by what it thinks it is talking
to.

**Every endpoint the monitor needs is refused.** The venue page, which the
provider scrapes for `rid` and the CSRF token, is refused by both clients. The
GraphQL endpoint that would return availability answers 403.

### So the parser was never the blocker

The point of the exercise was to see a real response and correct the parser
against it. The real response is a 403 and a reset connection. Nothing reaches
the parser, so whether it matches OpenTable's schema is both unanswerable and
no longer the question. The OpenTable tests still encode an assumed shape; they
should not be "corrected" against a guess, and there is nothing else to correct
them against.

### Where this stops

What remains technically is driving a real browser or impersonating a browser's
TLS fingerprint. That is not a workaround for a bug — it is evasion of an access
control the operator deliberately deployed, against exactly the activity it
exists to stop. Step 2 of this handoff already said to report rather than work
around, and that still holds; the earlier note that the ban on headless browsers
"no longer follows" was about the technical premise being void, and this section
supplies a different reason to stay on this side of it.

Sanctioned routes to the same goal, in rough order of odds: OpenTable's own
notify/waitlist alerts for a fully-booked restaurant; the restaurant's phone
line, which takes reservations directly and is usually faster on a cancellation
than any poller; and a reminder set for the release date roughly a year ahead,
which beats hunting cancellations and needs no access to OpenTable at all.

The code in this repo — config, matching, state, notification, the 65 tests —
is sound and was never the problem. It is left as is.
