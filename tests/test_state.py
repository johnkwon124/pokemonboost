import datetime as dt

from reservation_monitor.state import State

NOW = dt.datetime(2026, 9, 1, 9, 0)


def test_first_sighting_notifies(tmp_path):
    state = State(tmp_path / "s.json")
    assert state.should_notify("slot-a", NOW, 24)


def test_repeat_within_window_is_suppressed(tmp_path):
    state = State(tmp_path / "s.json")
    state.mark_notified("slot-a", NOW)
    assert not state.should_notify("slot-a", NOW + dt.timedelta(hours=6), 24)
    assert state.should_notify("slot-a", NOW + dt.timedelta(hours=25), 24)


def test_state_survives_a_round_trip(tmp_path):
    path = tmp_path / "s.json"
    first = State(path)
    first.mark_notified("slot-a", NOW)
    first.save()
    assert not State(path).should_notify("slot-a", NOW, 24)


def test_corrupt_state_file_starts_clean(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json")
    assert State(path).should_notify("slot-a", NOW, 24)


def test_prune_drops_stale_records(tmp_path):
    state = State(tmp_path / "s.json")
    state.mark_notified("old", NOW - dt.timedelta(days=40))
    state.mark_notified("new", NOW)
    state.prune(NOW, keep_days=30)
    assert state.should_notify("old", NOW, 24)
    assert not state.should_notify("new", NOW, 24)


def test_heartbeat_fires_once_a_day_after_the_hour(tmp_path):
    state = State(tmp_path / "s.json")
    assert not state.should_heartbeat(NOW.replace(hour=7), 8)
    assert state.should_heartbeat(NOW.replace(hour=8), 8)
    state.mark_heartbeat(NOW.replace(hour=8))
    assert not state.should_heartbeat(NOW.replace(hour=11), 8)
    assert state.should_heartbeat(NOW + dt.timedelta(days=1), 8)


def test_heartbeat_can_be_switched_off(tmp_path):
    assert not State(tmp_path / "s.json").should_heartbeat(NOW, None)


def test_alert_waits_for_the_failure_threshold(tmp_path):
    state = State(tmp_path / "s.json")
    state.record_failure()
    state.record_failure()
    assert not state.should_alert(NOW, 3, 6)
    state.record_failure()
    assert state.should_alert(NOW, 3, 6)


def test_alert_respects_its_cooldown_and_success_resets(tmp_path):
    state = State(tmp_path / "s.json")
    for _ in range(3):
        state.record_failure()
    state.mark_alerted(NOW)
    assert not state.should_alert(NOW + dt.timedelta(hours=2), 3, 6)
    assert state.should_alert(NOW + dt.timedelta(hours=7), 3, 6)
    state.record_success(NOW)
    assert state.consecutive_failures == 0
    assert not state.should_alert(NOW + dt.timedelta(hours=7), 3, 6)


def test_scan_slice_rotates_and_covers_everything(tmp_path):
    state = State(tmp_path / "s.json")
    days = list(range(10))
    seen = []
    for _ in range(5):
        seen.extend(state.take_scan_slice(days, 4))
    # Two and a half passes: every date covered, in order, wrapping around.
    assert seen[:10] == days
    assert sorted(set(seen)) == days


def test_scan_slice_wraps_across_the_end(tmp_path):
    state = State(tmp_path / "s.json")
    days = list(range(5))
    assert state.take_scan_slice(days, 3) == [0, 1, 2]
    assert state.take_scan_slice(days, 3) == [3, 4, 0]
    assert state.take_scan_slice(days, 3) == [1, 2, 3]


def test_scan_slice_of_zero_or_oversize_takes_everything(tmp_path):
    state = State(tmp_path / "s.json")
    days = list(range(5))
    assert state.take_scan_slice(days, 0) == days
    assert state.take_scan_slice(days, 99) == days
    assert state.take_scan_slice([], 3) == []


def test_scan_cursor_survives_a_round_trip(tmp_path):
    path = tmp_path / "s.json"
    days = list(range(6))
    first = State(path)
    first.take_scan_slice(days, 2)
    first.save()
    assert State(path).take_scan_slice(days, 2) == [2, 3]
