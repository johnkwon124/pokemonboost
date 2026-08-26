"""Persisted run-to-run state: which slots were already emailed about.

The monitor runs on ephemeral GitHub Actions runners, so this file is carried
between runs by actions/cache. Losing it costs at most one duplicate email.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

DEFAULT_STATE_PATH = Path(".monitor-state/state.json")


class State:
    def __init__(self, path: str | Path = DEFAULT_STATE_PATH) -> None:
        self.path = Path(path)
        self._data: dict[str, Any] = {
            "notified": {},
            "last_heartbeat_date": None,
            "last_success_at": None,
            "consecutive_failures": 0,
            "last_alert_at": None,
        }
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text())
                if isinstance(loaded, dict):
                    self._data.update(loaded)
            except (json.JSONDecodeError, OSError):
                # A corrupt cache is not worth failing a run over; start clean.
                pass

    # -- notification de-duplication ------------------------------------

    def should_notify(self, slot_key: str, now: dt.datetime, renotify_after_hours: int) -> bool:
        stamp = self._data["notified"].get(slot_key)
        if not stamp:
            return True
        try:
            last = dt.datetime.fromisoformat(stamp)
        except ValueError:
            return True
        return now - last >= dt.timedelta(hours=renotify_after_hours)

    def mark_notified(self, slot_key: str, now: dt.datetime) -> None:
        self._data["notified"][slot_key] = now.isoformat(timespec="seconds")

    def prune(self, now: dt.datetime, keep_days: int = 30) -> None:
        """Drop notification records older than the re-notify horizon."""
        cutoff = now - dt.timedelta(days=keep_days)
        kept = {}
        for key, stamp in self._data["notified"].items():
            try:
                if dt.datetime.fromisoformat(stamp) >= cutoff:
                    kept[key] = stamp
            except ValueError:
                continue
        self._data["notified"] = kept

    # -- heartbeat -------------------------------------------------------

    def should_heartbeat(self, now: dt.datetime, hour: int | None) -> bool:
        if hour is None:
            return False
        if now.hour < hour:
            return False
        return self._data.get("last_heartbeat_date") != now.date().isoformat()

    def mark_heartbeat(self, now: dt.datetime) -> None:
        self._data["last_heartbeat_date"] = now.date().isoformat()

    # -- failure tracking ------------------------------------------------

    def record_success(self, now: dt.datetime) -> None:
        self._data["last_success_at"] = now.isoformat(timespec="seconds")
        self._data["consecutive_failures"] = 0

    def record_failure(self) -> int:
        self._data["consecutive_failures"] = int(self._data.get("consecutive_failures", 0)) + 1
        return self._data["consecutive_failures"]

    def should_alert(self, now: dt.datetime, threshold: int, cooldown_hours: int) -> bool:
        if int(self._data.get("consecutive_failures", 0)) < threshold:
            return False
        stamp = self._data.get("last_alert_at")
        if not stamp:
            return True
        try:
            last = dt.datetime.fromisoformat(stamp)
        except ValueError:
            return True
        return now - last >= dt.timedelta(hours=cooldown_hours)

    def mark_alerted(self, now: dt.datetime) -> None:
        self._data["last_alert_at"] = now.isoformat(timespec="seconds")

    @property
    def last_success_at(self) -> str | None:
        return self._data.get("last_success_at")

    @property
    def consecutive_failures(self) -> int:
        return int(self._data.get("consecutive_failures", 0))

    # -- persistence -----------------------------------------------------

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True))
