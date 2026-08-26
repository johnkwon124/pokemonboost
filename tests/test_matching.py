import datetime as dt

from reservation_monitor.matching import candidate_dates, match_slot, match_slots
from reservation_monitor.models import Slot, Target

FRI_7PM = Target(weekday=4, at=dt.time(19, 0), tolerance_minutes=30)
SAT_4PM = Target(weekday=5, at=dt.time(16, 0), tolerance_minutes=30)
SUN_4PM = Target(weekday=6, at=dt.time(16, 0), tolerance_minutes=30)
TARGETS = [FRI_7PM, SAT_4PM, SUN_4PM]


def slot(text: str) -> Slot:
    return Slot(start=dt.datetime.fromisoformat(text), party_size=3)


def test_candidate_dates_only_target_weekdays():
    days = candidate_dates(TARGETS, dt.date(2026, 10, 1), dt.date(2026, 10, 14))
    assert days == [
        dt.date(2026, 10, 2), dt.date(2026, 10, 3), dt.date(2026, 10, 4),
        dt.date(2026, 10, 9), dt.date(2026, 10, 10), dt.date(2026, 10, 11),
    ]
    assert all(d.weekday() in (4, 5, 6) for d in days)


def test_candidate_dates_empty_when_range_inverted():
    assert candidate_dates(TARGETS, dt.date(2026, 10, 5), dt.date(2026, 10, 1)) == []


def test_exact_hit_on_friday():
    match = match_slot(slot("2026-10-02T19:00"), TARGETS)
    assert match is not None and match.exact and match.target is FRI_7PM


def test_near_hit_inside_tolerance():
    match = match_slot(slot("2026-10-02T18:45"), TARGETS)
    assert match is not None
    assert match.delta_minutes == -15
    assert not match.exact


def test_outside_tolerance_is_no_match():
    assert match_slot(slot("2026-10-02T20:15"), TARGETS) is None


def test_tolerance_boundary_is_inclusive():
    assert match_slot(slot("2026-10-02T19:30"), TARGETS) is not None
    assert match_slot(slot("2026-10-02T19:31"), TARGETS) is None


def test_right_time_but_wrong_weekday_is_no_match():
    # Thursday 7pm is not one of the targets.
    assert match_slot(slot("2026-10-01T19:00"), TARGETS) is None


def test_saturday_and_sunday_use_the_4pm_target():
    assert match_slot(slot("2026-10-03T16:00"), TARGETS).target is SAT_4PM
    assert match_slot(slot("2026-10-04T16:00"), TARGETS).target is SUN_4PM
    # 7pm on a Saturday is not what was asked for.
    assert match_slot(slot("2026-10-03T19:00"), TARGETS) is None


def test_matches_sorted_exact_first_then_soonest():
    slots = [
        slot("2026-11-06T18:40"),   # near
        slot("2026-12-04T19:00"),   # exact, later
        slot("2026-10-02T19:00"),   # exact, sooner
    ]
    ordered = [m.slot.start for m in match_slots(slots, TARGETS)]
    assert ordered == [
        dt.datetime(2026, 10, 2, 19, 0),
        dt.datetime(2026, 12, 4, 19, 0),
        dt.datetime(2026, 11, 6, 18, 40),
    ]


def test_zero_tolerance_demands_the_exact_minute():
    strict = [Target(weekday=4, at=dt.time(19, 0), tolerance_minutes=0)]
    assert match_slot(slot("2026-10-02T19:00"), strict) is not None
    assert match_slot(slot("2026-10-02T19:05"), strict) is None
