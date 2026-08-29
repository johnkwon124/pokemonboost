"""Entry point: ``python -m reservation_monitor <command>``."""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys
from zoneinfo import ZoneInfo

from .config import ConfigError, MonitorConfig, load_config
from .matching import candidate_dates, match_slots
from .notify import Mailer, NotifyError, availability_email, failure_email, heartbeat_email
from .providers import ProviderError, build_provider
from .release import build_ics, plan
from .state import DEFAULT_STATE_PATH, State


def _now(config: MonitorConfig) -> dt.datetime:
    return dt.datetime.now(ZoneInfo(config.venue.timezone)).replace(tzinfo=None)


def cmd_check(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    state = State(args.state)
    mailer = Mailer(config.notify.to)
    now = _now(config)

    if not config.enabled:
        print("monitor is disabled in config/reservation.yaml (enabled: false) — "
              "fill in restaurant.provider and restaurant.venue_id, then flip it to true")
        return 0

    start, end = config.clamp_to_today(now.date())
    all_days = candidate_dates(config.targets, start, end)
    days = state.take_scan_slice(all_days, config.scan.max_dates_per_run)
    scope = f"{len(days)} of {len(all_days)}" if len(days) != len(all_days) else f"{len(days)}"
    print(f"[{now:%Y-%m-%d %H:%M}] {config.venue.name}: checking {scope} candidate dates "
          f"({start} … {end}) for a party of {config.party_size}")

    try:
        provider = build_provider(config)
        slots = provider.collect(days, pause=config.scan.pause_seconds)
    except (ProviderError, ConfigError) as exc:
        failures = state.record_failure()
        print(f"error: {exc}", file=sys.stderr)
        if state.should_alert(
            now, config.notify.alert_after_consecutive_failures, config.notify.alert_cooldown_hours
        ):
            subject, text = failure_email(config, failures, str(exc))
            try:
                mailer.send(subject, text)
                state.mark_alerted(now)
            except NotifyError as mail_exc:
                print(f"error: could not send failure alert: {mail_exc}", file=sys.stderr)
        state.save()
        return 1

    state.record_success(now)
    matches = match_slots(slots, config.targets)
    print(f"  {len(slots)} seatings returned, {len(matches)} match the targets")

    fresh = [
        m for m in matches
        if state.should_notify(m.slot.key(), now, config.notify.renotify_after_hours)
    ]
    if fresh:
        subject, text, html = availability_email(config, fresh)
        mailer.send(subject, text, html)
        for match in fresh:
            state.mark_notified(match.slot.key(), now)
            print(f"  NOTIFIED  {match.describe()}")
    elif matches:
        print("  (all matches already e-mailed within the re-notify window)")

    if not fresh and state.should_heartbeat(now, config.notify.heartbeat_hour):
        subject, text = heartbeat_email(config, len(days), len(slots), now)
        try:
            mailer.send(subject, text)
            state.mark_heartbeat(now)
        except NotifyError as exc:
            print(f"warning: heartbeat mail failed: {exc}", file=sys.stderr)

    state.prune(now)
    state.save()
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """Dump every seating the provider returns, matching or not.

    This is the tool for confirming a venue id and endpoint shape without
    waiting for a real cancellation to appear.
    """
    config = load_config(args.config)
    now = _now(config)
    start, end = config.clamp_to_today(now.date())
    if args.days:
        end = min(end, start + dt.timedelta(days=args.days))
    days = candidate_dates(config.targets, start, end) if not args.all_days else _all_days(start, end)

    provider = build_provider(config)
    provider.capture_raw = bool(args.dump)
    try:
        slots = provider.collect(days, pause=config.scan.pause_seconds)
    finally:
        # The failing run is the one worth keeping: a probe that errors, or
        # returns nothing where the website plainly shows times, cannot be
        # diagnosed from its own stdout. Written on the way out either way.
        if args.dump:
            count = provider.write_captures(args.dump)
            print(f"wrote {count} raw exchange(s) to {args.dump}")
    if not slots:
        print(f"no seatings returned for {len(days)} dates ({start} … {end})")
        if not args.dump:
            print("re-run with --dump raw.json to capture what the server actually sent")
        return 0
    for slot in sorted(slots, key=lambda s: s.start):
        print(f"{slot.start:%a %Y-%m-%d %H:%M}  party={slot.party_size}  {slot.table_type}")
    print(f"\n{len(slots)} seatings across {len(days)} dates")
    matches = match_slots(slots, config.targets)
    print(f"{len(matches)} of them match your targets")
    return 0


def cmd_release_dates(args: argparse.Namespace) -> int:
    """Write a calendar of the moments target dates open for booking.

    Availability polling needs the booking platform to answer. This does not:
    the release moment falls out of the target date and the venue's lead time,
    so it can be computed now and handed to a calendar that fires on its own.
    """
    config = load_config(args.config)
    rule = config.release
    tz = config.venue.timezone
    start = _as_date_arg(args.since) or config.start_date
    end = _as_date_arg(args.until) or config.end_date
    if end < start:
        print(f"error: --until {end} is before --since {start}", file=sys.stderr)
        return 1

    targets = candidate_dates(config.targets, start, end)
    upcoming, passed = plan(targets, rule, tz, now=_now(config).replace(tzinfo=ZoneInfo(tz)))

    print(
        f"{config.venue.name}: {len(targets)} target dates in {start} … {end}, "
        f"assuming booking opens {rule.lead_days} days ahead at {rule.open_time:%H:%M} {tz}"
    )
    if passed:
        print(
            f"  {len(passed)} already opened — the earliest was "
            f"{passed[0].opens_at:%Y-%m-%d %H:%M}, so no reminder is possible for those"
        )
    if not upcoming:
        print(
            "\nnothing to remind you about: every date in this window opened in the past.\n"
            "Pick a window at least the lead time out, e.g.\n"
            f"  --since {(_now(config).date() + dt.timedelta(days=rule.lead_days)).isoformat()}"
        )
        return 0

    for release in upcoming:
        print(
            f"  {release.target:%a %Y-%m-%d}  opens  {release.opens_at:%a %Y-%m-%d %H:%M %Z}"
        )

    ics = build_ics(
        upcoming,
        venue_name=config.venue.name,
        party_size=config.party_size,
        booking_url=config.venue.profile_url or config.venue.url,
        rule=rule,
    )
    out = pathlib.Path(args.out)
    out.write_text(ics, newline="")
    print(f"\n{len(upcoming)} reminders written to {out}")
    if rule.assumed:
        print(
            "The lead time is assumed, not confirmed. Check it with the restaurant "
            "before trusting a year of reminders, then set release.assumed: false."
        )
    return 0


def _as_date_arg(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"expected YYYY-MM-DD, got {value!r}") from exc


def cmd_diagnose(args: argparse.Namespace) -> int:
    """Report how the booking host responds to different request shapes."""
    from .diagnose import run

    return run(timeout=args.timeout)


def cmd_test_email(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    now = _now(config)
    subject, text = heartbeat_email(config, 0, 0, now)
    Mailer(config.notify.to).send(f"[test] {subject}", text)
    print(f"sent to {', '.join(config.notify.to)}")
    return 0


def _all_days(start: dt.date, end: dt.date) -> list[dt.date]:
    out, day = [], start
    while day <= end:
        out.append(day)
        day += dt.timedelta(days=1)
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reservation_monitor", description=__doc__)
    parser.add_argument("--config", default=None, help="path to reservation.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="run one scan and e-mail anything new")
    check.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    check.set_defaults(func=cmd_check)

    probe = sub.add_parser("probe", help="print every seating the provider returns")
    probe.add_argument("--days", type=int, default=0, help="limit to the next N days")
    probe.add_argument("--all-days", action="store_true", help="ignore target weekdays")
    probe.add_argument(
        "--dump",
        default=None,
        metavar="PATH",
        help="write every raw HTTP exchange to PATH as JSON, errors included",
    )
    probe.set_defaults(func=cmd_probe)

    diagnose = sub.add_parser(
        "diagnose", help="report how the booking host responds to us (bot-block triage)"
    )
    diagnose.add_argument("--timeout", type=float, default=15.0)
    diagnose.set_defaults(func=cmd_diagnose)

    release = sub.add_parser(
        "release-dates",
        help="calendar reminders for when target dates open for booking",
    )
    release.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                        help="override the config's date_range.start")
    release.add_argument("--until", default=None, metavar="YYYY-MM-DD",
                        help="override the config's date_range.end")
    release.add_argument("--out", default="releases.ics", metavar="PATH",
                        help="where to write the .ics file (default: releases.ics)")
    release.set_defaults(func=cmd_release_dates)

    test = sub.add_parser("test-email", help="send yourself one message to verify SMTP")
    test.set_defaults(func=cmd_test_email)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ProviderError, NotifyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
