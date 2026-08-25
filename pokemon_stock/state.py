"""Persisted watch state so restarts do not replay old restock alerts."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class ProductState:
    available: bool = False
    last_status: str = ""
    last_alert_ts: float = 0.0
    last_checked_ts: float = 0.0


@dataclass
class WatchState:
    products: dict[str, ProductState] = field(default_factory=dict)

    def get(self, tcin: str) -> ProductState:
        return self.products.setdefault(tcin, ProductState())


def load_state(path: Path) -> WatchState:
    if not path.exists():
        return WatchState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # A corrupt state file only costs us one duplicate alert; never fatal.
        log.warning("상태 파일을 읽을 수 없어 새로 시작합니다 (%s): %s", path, exc)
        return WatchState()

    state = WatchState()
    for tcin, values in (raw.get("products") or {}).items():
        if not isinstance(values, dict):
            continue
        state.products[str(tcin)] = ProductState(
            available=bool(values.get("available", False)),
            last_status=str(values.get("last_status", "")),
            last_alert_ts=float(values.get("last_alert_ts", 0.0)),
            last_checked_ts=float(values.get("last_checked_ts", 0.0)),
        )
    return state


def save_state(path: Path, state: WatchState) -> None:
    payload = {
        "updated_at": time.time(),
        "products": {tcin: asdict(ps) for tcin, ps in state.products.items()},
    }
    parent = path.parent if str(path.parent) else Path(".")
    parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename so a crash mid-write cannot truncate the state file.
    fd, tmp_name = tempfile.mkstemp(dir=parent, prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
