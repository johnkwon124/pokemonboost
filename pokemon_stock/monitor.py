"""Polling loop: check each watched product, alert on out-of-stock → in-stock."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Callable

from pokemon_stock.config import Config, WatchItem
from pokemon_stock.models import ProductStock
from pokemon_stock.notifiers import Alert, Notifier, build_notifiers, dispatch
from pokemon_stock.state import ProductState, WatchState, load_state, save_state
from pokemon_stock.target_client import TargetApiError, TargetClient

log = logging.getLogger(__name__)


@dataclass
class PollResult:
    item: WatchItem
    stock: ProductStock | None = None
    error: str | None = None
    alerted: bool = False

    @property
    def ok(self) -> bool:
        return self.stock is not None


def should_alert(
    previous: ProductState,
    now_available: bool,
    now: float,
    realert_after_minutes: int,
) -> bool:
    """Alert on the rising edge, and optionally repeat while still in stock."""
    if not now_available:
        return False
    if not previous.available:
        return True
    if realert_after_minutes <= 0:
        return False
    return (now - previous.last_alert_ts) >= realert_after_minutes * 60


class Monitor:
    def __init__(
        self,
        config: Config,
        client: TargetClient | None = None,
        notifiers: list[Notifier] | None = None,
        state: WatchState | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.client = client or TargetClient(config)
        self.notifiers = build_notifiers(config) if notifiers is None else notifiers
        self.state = state if state is not None else load_state(config.state_file)
        self.sleep = sleeper
        self.clock = clock
        self._persist = state is None

    # ------------------------------------------------------------- polling

    def check_once(self) -> list[PollResult]:
        results = [self._check_product(item) for item in self.config.products]
        if self._persist:
            save_state(self.config.state_file, self.state)
        return results

    def _check_product(self, item: WatchItem) -> PollResult:
        try:
            stock = self.client.fetch_stock(item.tcin)
        except TargetApiError as exc:
            log.error("%s 조회 실패: %s", item.display(), exc)
            return PollResult(item=item, error=str(exc))

        now = self.clock()
        previous = self.state.get(item.tcin)
        available = stock.is_buyable(self.config.channels)
        alerted = should_alert(previous, available, now, self.config.realert_after_minutes)

        if alerted:
            label = item.display(stock.title)
            dispatch(self.notifiers, Alert(stock=stock, channels=self.config.channels, label=label))
        elif previous.available and not available:
            log.info("%s 품절 전환", item.display(stock.title))

        previous.available = available
        previous.last_status = stock.summary(self.config.channels)
        previous.last_checked_ts = now
        if alerted:
            previous.last_alert_ts = now

        log.info(
            "%s → %s%s",
            item.display(stock.title),
            previous.last_status,
            " [알림 발송]" if alerted else "",
        )
        return PollResult(item=item, stock=stock, alerted=alerted)

    # ---------------------------------------------------------------- loop

    def run(self, max_cycles: int | None = None) -> int:
        """Poll forever (or `max_cycles` times). Returns the cycles completed."""
        log.info(
            "%d개 상품 감시 시작 (주기 %ds ±%ds, 채널: %s)",
            len(self.config.products),
            self.config.interval_seconds,
            self.config.jitter_seconds,
            ", ".join(c.value for c in self.config.channels),
        )
        cycles = 0
        consecutive_failures = 0
        try:
            while max_cycles is None or cycles < max_cycles:
                results = self.check_once()
                cycles += 1

                if results and all(not r.ok for r in results):
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        log.error(
                            "%d회 연속 전체 조회 실패 — API key 또는 네트워크를 확인하세요.",
                            consecutive_failures,
                        )
                else:
                    consecutive_failures = 0

                if max_cycles is not None and cycles >= max_cycles:
                    break
                self.sleep(self._next_delay(consecutive_failures))
        except KeyboardInterrupt:
            log.info("사용자 중단 — 상태를 저장하고 종료합니다.")
            if self._persist:
                save_state(self.config.state_file, self.state)
        return cycles

    def _next_delay(self, consecutive_failures: int) -> float:
        """Jittered interval; back off when Target is refusing us outright."""
        base = self.config.interval_seconds * (2 ** min(consecutive_failures, 3))
        jitter = random.uniform(-self.config.jitter_seconds, self.config.jitter_seconds)
        return max(30.0, base + jitter)
