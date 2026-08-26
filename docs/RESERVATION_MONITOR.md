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
| Cadence | every 10 min, full quarter covered every ~30 min |
| Notify | jkwon47@gmail.com |

## What this is actually hunting

House of Prime Rib releases reservations about a year ahead, so October through
December is already booked solid. Nothing new will be "released" in that window
— every table this finds will be a **cancellation**. Those get re-taken within
minutes, which is why the monitor polls rather than checks daily, and why the
e-mail links straight to the booking page.

Saturday and Sunday 4:00 pm is the first seating of the day (the dining room
runs 5–10 pm Mon–Fri, 4–10 pm Sat–Sun), so those targets sit right at open.

## Setup

### 1. Merge this branch into the default branch — required

GitHub only runs `schedule` workflows from the repository's **default branch**.
This repo's default branch is `claude/develop-ai-workflow-9F2TL`. Until
`.github/workflows/reservation-monitor.yml` lands there, the monitor will not
run on a timer, no matter what the cron says.

### 2. Add the Gmail app password

Gmail needs an *app password*, not the account password: Google Account →
Security → 2-Step Verification → App passwords → create one for "Mail".

Under **Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|---|---|
| `SMTP_USER` | `jkwon47@gmail.com` |
| `SMTP_PASSWORD` | the 16-character app password |
| `NOTIFY_TO` | *(optional)* overrides `notify.to` in the config |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM` | *(optional)* defaults are `smtp.gmail.com` / `587` / `SMTP_USER` |

That is the only credential needed. There is deliberately no OpenTable secret
to manage — see below.

### 3. Confirm it works

**Actions → Reservation monitor → Run workflow**, with *probe* ticked. That
prints every seating OpenTable returns instead of e-mailing, which is how to
confirm the restaurant resolved correctly without waiting for a real
cancellation. Run it again unticked to get a live check.

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

```bash
pip install -r requirements-monitor.txt

# One scan; e-mails anything new. DRY_RUN prints instead of sending.
DRY_RUN=1 python -m reservation_monitor check

# Every seating OpenTable returns, matching or not.
python -m reservation_monitor probe --days 21 --all-days

# Send one message to prove SMTP works.
SMTP_USER=... SMTP_PASSWORD=... python -m reservation_monitor test-email
```

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

- **State lives in the Actions cache.** Runners are destroyed after each run,
  so the "already told you about this one" record and the scan cursor ride
  along in `actions/cache` under a rotating key. If the cache is evicted the
  worst case is one duplicate e-mail and a reset cursor.
- **GitHub's scheduler is best effort.** Runs get skipped when the shared queue
  is busy, so treat 10 minutes as a floor rather than a guarantee. The repo is
  public, so Actions minutes are free.
- **Scheduled workflows are disabled after 60 days without repository
  activity.** GitHub warns by e-mail first; any commit re-arms it.
- **Daily heartbeat.** At `notify.heartbeat_hour` (8 am PT) you get one "still
  watching, nothing yet" e-mail, so silence always means *no availability*
  rather than *the monitor died*.
- **This only watches.** It does not hold or book a table. Walk-ins and the bar
  remain the other route in.

## Watching something else

`config/reservation.yaml` drives all of it, and adapters for Resy, Tock and
SevenRooms ship alongside the OpenTable one. To watch a second venue, copy the
config and add a job to the workflow with `RESERVATION_CONFIG=config/other.yaml`
and its own cache path.
