import json

from pokemon_stock.state import ProductState, WatchState, load_state, save_state


def test_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    state = WatchState()
    state.products["123"] = ProductState(
        available=True, last_status="배송 IN_STOCK", last_alert_ts=100.0, last_checked_ts=101.0
    )
    save_state(path, state)

    loaded = load_state(path)
    assert loaded.products["123"].available is True
    assert loaded.products["123"].last_alert_ts == 100.0


def test_missing_file_starts_empty(tmp_path):
    assert load_state(tmp_path / "nope.json").products == {}


def test_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_state(path).products == {}


def test_bad_entries_are_skipped(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"products": {"1": "oops", "2": {"available": True}}}), encoding="utf-8")
    loaded = load_state(path)
    assert "1" not in loaded.products
    assert loaded.products["2"].available is True


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "state.json"
    save_state(path, WatchState())
    assert path.exists()


def test_save_leaves_no_temp_files(tmp_path):
    path = tmp_path / "state.json"
    save_state(path, WatchState())
    save_state(path, WatchState())
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_get_creates_default_entry():
    state = WatchState()
    entry = state.get("999")
    assert entry.available is False
    assert state.products["999"] is entry
