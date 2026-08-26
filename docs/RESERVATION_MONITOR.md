# Reservation monitor

Watches one restaurant's booking platform for the seatings you actually want
and e-mails you the moment one opens up. Cancellations get re-booked within
minutes, so it polls every 10 minutes from GitHub Actions rather than from a
laptop that might be asleep.

Current watch (`config/reservation.yaml`):

| | |
|---|---|
| Party size | 3 |
| Friday | 7:00 pm PT (±30 min) |
| Saturday | 4:00 pm PT (±30 min) |
| Sunday | 4:00 pm PT (±30 min) |
| Window | 2026-10-01 → 2026-12-31 |
| Notify | jkwon47@gmail.com |

## Setup

Three things to fill in. Until step 1 is done, `enabled: false` keeps the
scheduled job quiet.

### 1. Identify the restaurant and its booking platform

Open the restaurant on Google Maps and click through to its reservation link.
The destination tells you the `provider`, and the URL contains the `venue_id`:

| Platform | Booking URL looks like | `venue_id` to use |
|---|---|---|
| Resy | `resy.com/cities/sf/somewhere-good` | numeric venue id (see below) |
| OpenTable | `opentable.com/r/somewhere-good` | numeric `rid` |
| Tock | `exploretock.com/somewhere-good` | the slug, `somewhere-good` |
| SevenRooms | `sevenrooms.com/reservations/somewhereGood` | the slug |

Resy hides its numeric id: open the restaurant page, open browser devtools →
Network, filter for `api.resy.com`, and read `venue_id` off any request. The
OpenTable `rid` shows up the same way, or in the page source as
`"restaurantId"`.

Then set `restaurant.provider`, `restaurant.venue_id` and `restaurant.name`
in `config/reservation.yaml`, and flip `enabled` to `true`.

### 2. Add the API credential (Resy and OpenTable only)

Tock and SevenRooms need nothing. The other two need a token that their own
web app sends, copied from the same devtools Network tab:

| Platform | Where to copy it from | Repository secret |
|---|---|---|
| Resy | `Authorization: ResyAPI api_key="…"` header | `RESY_API_KEY` |
| Resy (private venues) | `X-Resy-Auth-Token` header while signed in | `RESY_AUTH_TOKEN` |
| OpenTable | `x-csrf-token` header on the POST to `/dapi/fe/gql` | `OPENTABLE_AUTH_TOKEN` |
| OpenTable | the `Cookie` header on that same request | `OPENTABLE_COOKIE` |

These rotate. When one expires the monitor starts failing and, after three
failed runs, e-mails you to say so — it will not go quietly blind.

### 3. Add the e-mail credential

Gmail needs an *app password*, not your account password: Google Account →
Security → 2-Step Verification → App passwords → create one for "Mail".

Add these under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `SMTP_USER` | `jkwon47@gmail.com` |
| `SMTP_PASSWORD` | the 16-character app password |
| `NOTIFY_TO` | *(optional)* overrides `notify.to` in the config |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM` | *(optional)* defaults are `smtp.gmail.com` / `587` / `SMTP_USER` |

Verify with **Actions → Reservation monitor → Run workflow**, or locally:

```bash
pip install -r requirements-monitor.txt
SMTP_USER=... SMTP_PASSWORD=... python -m reservation_monitor test-email
```

## Running it by hand

```bash
# One scan; e-mails anything new. DRY_RUN prints instead of sending.
DRY_RUN=1 python -m reservation_monitor check

# Every seating the platform returns, matching or not — use this to confirm
# the venue id is right without waiting for a real cancellation.
python -m reservation_monitor probe --days 21 --all-days

# Send one message to prove SMTP works.
python -m reservation_monitor test-email
```

## How it decides what to tell you

1. `candidate_dates` expands the date window to only Fridays, Saturdays and
   Sundays — about 39 dates across the quarter instead of 92.
2. The provider queries those dates. Resy first calls its calendar endpoint,
   which reports a whole range in one request, and only asks for seatings on
   days that have any inventory at all.
3. `match_slots` keeps seatings within `tolerance_minutes` of a target time on
   that target's weekday. Exact hits sort first.
4. Anything not already e-mailed within `renotify_after_hours` gets sent, with
   a direct booking link per slot.

## Things worth knowing

- **State lives in the Actions cache.** The runner is destroyed after each run,
  so the "already told you about this one" record rides along in
  `actions/cache` under a rotating key. If the cache is evicted the worst case
  is one duplicate e-mail.
- **GitHub's scheduler is best effort.** Runs are skipped when the shared queue
  is busy, so treat 10 minutes as a floor, not a guarantee. On a private repo
  this also spends Actions minutes — roughly 140 runs a day. Widening the cron
  to `*/30` cuts that by two thirds if it becomes a problem.
- **Scheduled workflows are disabled after 60 days without repository
  activity.** GitHub e-mails a warning first; pushing any commit re-arms it.
- **Daily heartbeat.** At `notify.heartbeat_hour` (8 am venue time) you get one
  "still watching, nothing yet" e-mail, so silence always means *no
  availability* rather than *the monitor died*.
- **This only watches.** It does not hold or book a table — the e-mail links
  straight to the booking page, and you finish it there.

## Adding another restaurant or a different time

`config/reservation.yaml` drives all of it. To watch a second venue, copy the
file, and add a second job to the workflow with
`RESERVATION_CONFIG=config/other.yaml` and a distinct cache path.
