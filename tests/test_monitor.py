import pytest

from pokemon_stock.config import Config, WatchItem
from pokemon_stock.models import Availability, Channel, ProductStock, StoreStock
from pokemon_stock.monitor import Monitor, should_alert
from pokemon_stock.notifiers.base import Alert, Notifier
from pokemon_stock.state import ProductState, WatchState
from pokemon_stock.target_client import TargetApiError


class RecordingNotifier(Notifier):
    name = "recording"

    def __init__(self):
        self.alerts: list[Alert] = []

    def send(self, alert: Alert) -> None:
        self.alerts.append(alert)


class ExplodingNotifier(Notifier):
    name = "exploding"

    def send(self, alert: Alert) -> None:
        raise RuntimeError("채널 장애")


class FakeClient:
    """Replays a scripted sequence of stock states (or errors) per call."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def fetch_stock(self, tcin: str) -> ProductStock:
        self.calls += 1
        entry = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(entry, Exception):
            raise entry
        return entry


def stock(shipping=Availability.OUT_OF_STOCK, pickup=None, tcin="94300072") -> ProductStock:
    stores = []
    if pickup is not None:
        stores = [StoreStock(store_id="1234", store_name="Palo Alto", availability=pickup)]
    return ProductStock(
        tcin=tcin,
        title="Booster Bundle",
        url=f"https://www.target.com/p/A-{tcin}",
        price="$26.99",
        shipping=shipping,
        stores=stores,
    )


def make_config(**overrides) -> Config:
    config = Config(products=[WatchItem(tcin="94300072", label="번들")])
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def make_monitor(script, config=None, notifier=None, clock_values=None):
    notifier = notifier or RecordingNotifier()
    ticks = iter(clock_values) if clock_values else None
    clock = (lambda: next(ticks)) if ticks else (lambda: 1000.0)
    monitor = Monitor(
        config or make_config(),
        client=FakeClient(script),
        notifiers=[notifier],
        state=WatchState(),
        sleeper=lambda _: None,
        clock=clock,
    )
    return monitor, notifier


# ----------------------------------------------------------- transition rule


@pytest.mark.parametrize(
    "was_available,now_available,expected",
    [(False, True, True), (False, False, False), (True, True, False), (True, False, False)],
)
def test_should_alert_only_on_rising_edge(was_available, now_available, expected):
    previous = ProductState(available=was_available, last_alert_ts=0.0)
    assert should_alert(previous, now_available, now=100.0, realert_after_minutes=0) is expected


def test_should_alert_repeats_after_realert_window():
    previous = ProductState(available=True, last_alert_ts=0.0)
    assert should_alert(previous, True, now=59 * 60, realert_after_minutes=60) is False
    assert should_alert(previous, True, now=60 * 60, realert_after_minutes=60) is True


# ------------------------------------------------------------------ polling


def test_alerts_once_when_product_comes_back_in_stock():
    monitor, notifier = make_monitor(
        [stock(Availability.OUT_OF_STOCK), stock(Availability.IN_STOCK), stock(Availability.IN_STOCK)]
    )
    assert monitor.check_once()[0].alerted is False
    assert notifier.alerts == []

    assert monitor.check_once()[0].alerted is True
    assert len(notifier.alerts) == 1

    assert monitor.check_once()[0].alerted is False
    assert len(notifier.alerts) == 1


def test_alerts_again_after_going_out_of_stock_and_back():
    monitor, notifier = make_monitor(
        [
            stock(Availability.IN_STOCK),
            stock(Availability.OUT_OF_STOCK),
            stock(Availability.IN_STOCK),
        ]
    )
    for _ in range(3):
        monitor.check_once()
    assert len(notifier.alerts) == 2


def test_first_check_of_an_in_stock_product_alerts():
    monitor, notifier = make_monitor([stock(Availability.IN_STOCK)])
    monitor.check_once()
    assert len(notifier.alerts) == 1
    assert notifier.alerts[0].label == "번들"
    assert "$26.99" in notifier.alerts[0].body


def test_alert_falls_back_to_product_title_without_label():
    config = make_config(products=[WatchItem(tcin="94300072")])
    monitor, notifier = make_monitor([stock(Availability.IN_STOCK)], config=config)
    monitor.check_once()
    assert notifier.alerts[0].label == "Booster Bundle"


def test_unknown_status_never_triggers_an_alert():
    monitor, notifier = make_monitor([stock(Availability.UNKNOWN)])
    monitor.check_once()
    assert notifier.alerts == []


def test_pickup_channel_ignores_shipping_stock():
    config = make_config(channels=[Channel.PICKUP], store_ids=["1234"])
    monitor, notifier = make_monitor(
        [
            stock(Availability.IN_STOCK, pickup=Availability.OUT_OF_STOCK),
            stock(Availability.OUT_OF_STOCK, pickup=Availability.IN_STOCK),
        ],
        config=config,
    )
    monitor.check_once()
    assert notifier.alerts == []
    monitor.check_once()
    assert len(notifier.alerts) == 1


def test_realert_uses_configured_window():
    config = make_config(realert_after_minutes=30)
    monitor, notifier = make_monitor(
        [stock(Availability.IN_STOCK)] * 3,
        config=config,
        clock_values=[0.0, 10 * 60, 31 * 60],
    )
    monitor.check_once()
    monitor.check_once()
    monitor.check_once()
    assert len(notifier.alerts) == 2


def test_api_error_is_reported_without_touching_state():
    monitor, notifier = make_monitor(
        [stock(Availability.IN_STOCK), TargetApiError("HTTP 503"), stock(Availability.IN_STOCK)]
    )
    monitor.check_once()
    result = monitor.check_once()[0]
    assert result.error == "HTTP 503"
    assert result.ok is False
    assert monitor.state.get("94300072").available is True  # unchanged by the failure
    monitor.check_once()
    assert len(notifier.alerts) == 1  # no duplicate alert after recovery


def test_a_broken_notifier_does_not_stop_the_others():
    good = RecordingNotifier()
    monitor = Monitor(
        make_config(),
        client=FakeClient([stock(Availability.IN_STOCK)]),
        notifiers=[ExplodingNotifier(), good],
        state=WatchState(),
        sleeper=lambda _: None,
    )
    monitor.check_once()
    assert len(good.alerts) == 1


# --------------------------------------------------------------------- loop


def test_run_stops_after_max_cycles_and_sleeps_between_them():
    delays: list[float] = []
    monitor = Monitor(
        make_config(),
        client=FakeClient([stock(Availability.OUT_OF_STOCK)]),
        notifiers=[],
        state=WatchState(),
        sleeper=delays.append,
    )
    assert monitor.run(max_cycles=3) == 3
    assert len(delays) == 2  # no sleep after the final cycle
    assert all(d >= 30 for d in delays)


def test_run_backs_off_when_every_check_fails():
    delays: list[float] = []
    config = make_config(interval_seconds=60, jitter_seconds=0)
    monitor = Monitor(
        config,
        client=FakeClient([TargetApiError("HTTP 403")]),
        notifiers=[],
        state=WatchState(),
        sleeper=delays.append,
    )
    monitor.run(max_cycles=3)
    assert delays == [120.0, 240.0]


def test_state_file_is_written_and_reused(tmp_path):
    config = make_config(state_file=tmp_path / "state.json")
    Monitor(
        config,
        client=FakeClient([stock(Availability.IN_STOCK)]),
        notifiers=[RecordingNotifier()],
        sleeper=lambda _: None,
    ).check_once()
    assert config.state_file.exists()

    second_notifier = RecordingNotifier()
    Monitor(
        config,
        client=FakeClient([stock(Availability.IN_STOCK)]),
        notifiers=[second_notifier],
        sleeper=lambda _: None,
    ).check_once()
    assert second_notifier.alerts == []  # restart must not replay the alert
