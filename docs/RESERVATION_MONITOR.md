# Reservation monitor — House of Prime Rib

Watches OpenTable for a table for three at House of Prime Rib and e-mails the
moment one appears.

| | |
|---|---|
| Restaurant | House of Prime Rib, 1906 Van Ness Ave, San Francisco |
| Platform | OpenTable (the only online option; otherwise 415-885-4605) |
| Party size | 3 |
| Friday | 7:00 pm PT (±30 min) |
| Saturday | 4:00 pm PT (±30 min) |
| Sunday | 4:00 pm PT (±30 min) |
| Window | 2026-10-01 → 2026-12-31 (39 candidate dates) |
| Cadence | every 15 min from a Mac, full quarter covered every ~45 min |
| Notify | jkwon47@gmail.com |

## What this is actually hunting

House of Prime Rib releases reservations about a year ahead, so October through
December is already booked solid. Nothing new will be "released" in that window
— every table this finds will be a **cancellation**. Those get re-taken within
minutes, which is why the monitor polls rather than checks daily, and why the
e-mail links straight to the booking page.

Saturday and Sunday 4:00 pm is the first seating of the day (the dining room
runs 5–10 pm Mon–Fri, 4–10 pm Sat–Sun), so those targets sit right at open.

## Why this does not run on GitHub Actions

It was built to, and it cannot. OpenTable tarpits every request from GitHub's
IP ranges: a live `diagnose` run found `robots.txt` — the static file every
crawler on the internet fetches — hanging for the full timeout, while
`example.com` answered in 0.0 seconds from the same runner. The apex domain,
the UK and Canada sites all behave the same way; `mobile-api.opentable.com`
returns an Akamai *Access Denied*; `api.opentable.com` will not open a
connection at all.

A block that catches `robots.txt` is keyed on the connecting IP, not on what
the request looks like, so no header set and no headless browser would change
it. The workflow is kept for manual `diagnose` runs in case that ever changes,
but its schedule is removed.

A home connection is not blocked, so the monitor runs from a Mac instead. Same
code, same config.

## Setup, on the Mac that will do the watching

```bash
git clone https://github.com/johnkwon124/pokemonboost.git
cd pokemonboost
./scripts/install-macos.sh
```

The installer does five things and stops at the first one that fails:

1. Creates a virtualenv and installs `requests` and `PyYAML`.
2. **Checks that this Mac can reach OpenTable**, and refuses to install a timer
   if it cannot — better to know now than to discover it through four months of
   silence.
3. Asks for the Gmail app password (Google Account → Security → 2-Step
   Verification → App passwords) and writes it to `~/.reservation-monitor/env`,
   `chmod 600`, outside the repository. This repo is public; no credential
   belongs in it.
4. Sends one test e-mail, so the mail path is proven before it is automated.
5. Installs a `launchd` agent that runs a scan every 15 minutes and restarts
   itself at login.

```
Watch it     tail -f ~/Library/Logs/reservation-monitor.log
Run one now  ./scripts/run-local.sh
Stop         launchctl unload ~/Library/LaunchAgents/com.jkwon.reservation-monitor.plist
Start        launchctl load ~/Library/LaunchAgents/com.jkwon.reservation-monitor.plist
```

### The Mac has to stay awake

`launchd` timers do not fire while the machine is asleep; a sleeping Mac
catches up with a single run on wake and misses everything in between. Keep it
plugged in, and in System Settings → Battery → Options turn on **Prevent
automatic sleeping on power adapter when the display is off**. Closing the lid
still sleeps most models, so leave it open or attach an external display.

The daily heartbeat is the check on this: if the 8am e-mail stops arriving, the
Mac slept or the agent was unloaded.

## Why there is no OpenTable API key to rotate

OpenTable's availability endpoint wants a CSRF token and session cookies. The
usual approach is to paste those out of browser devtools into a secret — but
they expire, and a four-month unattended watch would go quietly blind the day
they did.

Instead the provider loads the restaurant's own public page
(`https://www.opentable.com/house-of-prime-rib`) at the start of each run and
scrapes both the numeric restaurant id and a fresh token from it. Nothing to
look up, nothing to renew.

If OpenTable changes that page's markup the run fails loudly — and after three
consecutive failures you get an e-mail saying so. `OPENTABLE_AUTH_TOKEN` and
`OPENTABLE_COOKIE` still work as a manual override if that ever happens.

## Running it by hand

`scripts/run-local.sh` loads the credentials and picks the virtualenv, so
prefer it over calling Python directly:

```bash
./scripts/run-local.sh              # one scan; e-mails anything new
./scripts/run-local.sh probe        # every seating found, sends nothing
./scripts/run-local.sh probe --dump raw.json   # …and keep the raw responses
./scripts/run-local.sh diagnose     # can this machine reach OpenTable?
./scripts/run-local.sh release-dates --since 2027-10-01 --until 2027-12-31
                                    # calendar for when dates open for booking
./scripts/run-local.sh test-email   # prove SMTP still works
```

`DRY_RUN=1` makes any of them print the e-mail instead of sending it.

## How it decides what to tell you

1. The date window is expanded to Fridays, Saturdays and Sundays only — 39
   dates across the quarter instead of 92.
2. Each run takes the next 13 of those and the cursor rotates, so the full
   quarter is covered every three runs without hammering one endpoint 5,600
   times a day. Tune with `scan.max_dates_per_run`; set it to `0` to check
   everything every run.
3. Seatings within `tolerance_minutes` of a target time, on that target's
   weekday, count as matches. Exact hits sort first; near hits are labelled
   (`6:45 PM (-15 min vs target)`).
4. Anything not already e-mailed within `renotify_after_hours` gets sent, with
   a direct booking link per slot.

## Things worth knowing

- **State lives in `.monitor-state/`** next to the checkout — the record of what
  has already been e-mailed about, and the scan cursor. Deleting it costs at
  most one duplicate e-mail.
- **Nothing here costs money and nothing calls an LLM.** It is `requests`, a
  few regexes and `smtplib`. Running it for four months is free.
- **Daily heartbeat.** At `notify.heartbeat_hour` (8 am PT) you get one "still
  watching, nothing yet" e-mail, so silence always means *no availability*
  rather than *the monitor died*.
- **This only watches.** It does not hold or book a table. Walk-ins and the bar
  remain the other route in.

## Watching something else

`config/reservation.yaml` drives all of it, and adapters for Resy, Tock and
SevenRooms ship alongside the OpenTable one — those three are not known to
block datacenter traffic, so a venue on any of them could go back to running
on GitHub Actions. To watch a second venue, copy the config and point
`RESERVATION_CONFIG` at it.

## Release-date reminders

OpenTable refuses this client (see `docs/MAC_MINI_HANDOFF.md`), so the
availability watch cannot run. `release-dates` is the part of the goal that
needs no access to OpenTable at all: the moment a date opens for booking is
just the target date minus the venue's lead time, so it can be computed now and
handed to a calendar that fires on its own.

```bash
.venv/bin/python -m reservation_monitor release-dates \
  --since 2027-10-01 --until 2027-12-31 --out hopr.ics
```

It prints each target date with the instant it opens, and writes an `.ics` with
one alarmed event per date. Import it once (double-click on macOS); event UIDs
are derived from the venue and target date, so re-running and re-importing
updates those events rather than duplicating them.

Two things worth knowing:

- **The window has to be at least the lead time out.** Asking for a range whose
  releases have already passed produces no reminders — correctly, but silently
  if you are not reading. The command says how many already opened and suggests
  a workable `--since` rather than writing an empty calendar.
- **`release.lead_days` is an assumption.** The project notes say "about a year";
  nobody has confirmed the exact rule or the hour of day. Until someone does,
  every event carries that caveat in its description. Confirm it with the
  restaurant, set the real values, and set `release.assumed: false`.
