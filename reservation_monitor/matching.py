"""Turning the user's targets into concrete dates, and slots into matches."""

from __future__ import annotations

import datetime as dt

from .models import Match, Slot, Target


def candidate_dates(
    targets: list[Target],
    start: dt.date,
    end: dt.date,
) -> list[dt.date]:
    """Every date in [start, end] whose weekday one of the targets asks for.

    Only these dates are worth querying, which keeps a three-month window down
    to roughly forty requests instead of ninety.
    """
    wanted = {t.weekday for t in targets}
    out: list[dt.date] = []
    day = start
    while day <= end:
        if day.weekday() in wanted:
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def match_slot(slot: Slot, targets: list[Target]) -> Match | None:
    """Best (closest) target this slot satisfies, or None."""
    best: Match | None = None
    for target in targets:
        if slot.start.weekday() != target.weekday:
            continue
        target_dt = dt.datetime.combine(slot.day, target.at)
        delta = int(round((slot.start - target_dt).total_seconds() / 60))
        if abs(delta) > target.tolerance_minutes:
            continue
        if best is None or abs(delta) < abs(best.delta_minutes):
            best = Match(slot=slot, target=target, delta_minutes=delta)
    return best


def match_slots(slots: list[Slot], targets: list[Target]) -> list[Match]:
    """All matching slots, exact hits first, then by how soon they are."""
    matches = [m for m in (match_slot(s, targets) for s in slots) if m is not None]
    matches.sort(key=lambda m: (abs(m.delta_minutes), m.slot.start))
    return matches
