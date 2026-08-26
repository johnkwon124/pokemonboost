"""Entry point: ``python -m reservation_monitor <command>``."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from zoneinfo import ZoneInfo

from .config import ConfigError, MonitorConfig, load_config
from .matching import candidate_dates, match_slots
from .notify import Mailer, NotifyError, availability_email, failure_email, heartbeat_email
from .providers import ProviderError, build_provider
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
    days = candidate_dates(config.targets, start, end)
    print(f"[{now:%Y-%m-%d %H:%M}] {config.venue.name}: checking {len(days)} candidate dates "
          f"({start} … {end}) for a party of {config.party_size}")

    try:
        provider = build_provider(config)
        slots = provider.collect(days)
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
    slots = provider.collect(days)
    if not slots:
        print(f"no seatings returned for {len(days)} dates ({start} … {end})")
        return 0
    for slot in sorted(slots, key=lambda s: s.start):
        print(f"{slot.start:%a %Y-%m-%d %H:%M}  party={slot.party_size}  {slot.table_type}")
    print(f"\n{len(slots)} seatings across {len(days)} dates")
    matches = match_slots(slots, config.targets)
    print(f"{len(matches)} of them match your targets")
    return 0


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
    probe.set_defaults(func=cmd_probe)

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
