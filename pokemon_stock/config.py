"""Configuration loading: YAML file first, environment variables on top."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from pokemon_stock.models import Channel

# The public web client key target.com embeds in its own front-end bundle.
# It rotates occasionally; override with TARGET_API_KEY (see README) if the
# client starts returning 401/403.
DEFAULT_API_KEY = "9f36aeafbe60771e321a7cc95a78140772ab3e96"


class ConfigError(ValueError):
    """Raised when the config file is missing something the monitor needs."""


@dataclass
class WatchItem:
    """One product to watch."""

    tcin: str
    label: str = ""

    def display(self, fallback: str = "") -> str:
        return self.label or fallback or f"TCIN {self.tcin}"


@dataclass
class EmailConfig:
    enabled: bool = False
    host: str = "smtp.gmail.com"
    port: int = 587
    username: str = ""
    password: str = ""
    sender: str = ""
    recipients: list[str] = field(default_factory=list)
    use_tls: bool = True


@dataclass
class WebhookConfig:
    enabled: bool = False
    # Discord and Slack incoming webhooks both accept a JSON body with a
    # top-level "content"/"text" field; we send both keys.
    url: str = ""


@dataclass
class NotifyConfig:
    console: bool = True
    desktop: bool = False
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    email: EmailConfig = field(default_factory=EmailConfig)


@dataclass
class Config:
    products: list[WatchItem] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=lambda: [Channel.SHIPPING])
    store_ids: list[str] = field(default_factory=list)
    zip_code: str = "94301"
    state: str = "CA"
    latitude: float = 37.44
    longitude: float = -122.16
    interval_seconds: int = 180
    jitter_seconds: int = 45
    request_timeout: float = 15.0
    max_retries: int = 3
    api_key: str = DEFAULT_API_KEY
    state_file: Path = Path(".pokemon_stock_state.json")
    realert_after_minutes: int = 0
    notify: NotifyConfig = field(default_factory=NotifyConfig)

    def validate(self) -> None:
        if not self.products:
            raise ConfigError("watch할 상품이 없습니다. config의 products에 TCIN을 추가하세요.")
        if not self.channels:
            raise ConfigError("channels가 비어 있습니다. shipping / pickup 중 하나 이상 필요합니다.")
        if Channel.PICKUP in self.channels and not self.store_ids:
            raise ConfigError("pickup 채널을 쓰려면 store_ids에 매장 ID가 최소 하나 필요합니다.")
        if self.interval_seconds < 30:
            raise ConfigError("interval_seconds는 30초 이상이어야 합니다 (차단 방지).")

    @property
    def primary_store_id(self) -> str:
        """Store used for pricing/fulfillment context on every request."""
        return self.store_ids[0] if self.store_ids else "1234"


def _as_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "y", "on")


def _parse_products(raw: object) -> list[WatchItem]:
    items: list[WatchItem] = []
    for entry in raw or []:
        if isinstance(entry, dict):
            tcin = str(entry.get("tcin", "")).strip()
            label = str(entry.get("label", "")).strip()
        else:
            tcin, label = str(entry).strip(), ""
        if not tcin:
            raise ConfigError(f"products 항목에 tcin이 없습니다: {entry!r}")
        if not tcin.isdigit():
            raise ConfigError(f"TCIN은 숫자여야 합니다: {tcin!r}")
        items.append(WatchItem(tcin=tcin, label=label))
    return items


def _parse_channels(raw: object) -> list[Channel]:
    channels: list[Channel] = []
    for name in raw or []:
        key = str(name).strip().lower()
        try:
            channel = Channel(key)
        except ValueError:
            raise ConfigError(f"알 수 없는 channel: {name!r} (shipping 또는 pickup)") from None
        if channel not in channels:
            channels.append(channel)
    return channels


def load_config(path: str | Path | None = None) -> Config:
    """Load config.yaml (if present) and apply environment overrides."""
    data: dict = {}
    if path:
        config_path = Path(path)
        if not config_path.exists():
            raise ConfigError(f"설정 파일을 찾을 수 없습니다: {config_path}")
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ConfigError("설정 파일의 최상위는 매핑(YAML dict)이어야 합니다.")

    cfg = Config()
    if "products" in data:
        cfg.products = _parse_products(data["products"])
    if "channels" in data:
        cfg.channels = _parse_channels(data["channels"])
    if "store_ids" in data:
        cfg.store_ids = [str(s).strip() for s in data["store_ids"] if str(s).strip()]

    location = data.get("location") or {}
    cfg.zip_code = str(location.get("zip", cfg.zip_code))
    cfg.state = str(location.get("state", cfg.state))
    cfg.latitude = float(location.get("latitude", cfg.latitude))
    cfg.longitude = float(location.get("longitude", cfg.longitude))

    polling = data.get("polling") or {}
    cfg.interval_seconds = int(polling.get("interval_seconds", cfg.interval_seconds))
    cfg.jitter_seconds = int(polling.get("jitter_seconds", cfg.jitter_seconds))
    cfg.request_timeout = float(polling.get("request_timeout", cfg.request_timeout))
    cfg.max_retries = int(polling.get("max_retries", cfg.max_retries))
    cfg.realert_after_minutes = int(polling.get("realert_after_minutes", cfg.realert_after_minutes))

    if data.get("api_key"):
        cfg.api_key = str(data["api_key"])
    if data.get("state_file"):
        cfg.state_file = Path(str(data["state_file"]))

    notify = data.get("notify") or {}
    cfg.notify.console = bool(notify.get("console", cfg.notify.console))
    cfg.notify.desktop = bool(notify.get("desktop", cfg.notify.desktop))

    webhook = notify.get("webhook") or {}
    cfg.notify.webhook.url = str(webhook.get("url", "") or "")
    cfg.notify.webhook.enabled = bool(webhook.get("enabled", bool(cfg.notify.webhook.url)))

    email = notify.get("email") or {}
    cfg.notify.email.host = str(email.get("host", cfg.notify.email.host))
    cfg.notify.email.port = int(email.get("port", cfg.notify.email.port))
    cfg.notify.email.username = str(email.get("username", "") or "")
    cfg.notify.email.password = str(email.get("password", "") or "")
    cfg.notify.email.sender = str(email.get("sender", "") or cfg.notify.email.username)
    cfg.notify.email.recipients = [str(r) for r in (email.get("recipients") or [])]
    cfg.notify.email.use_tls = bool(email.get("use_tls", cfg.notify.email.use_tls))
    cfg.notify.email.enabled = bool(email.get("enabled", False))

    _apply_env(cfg)
    return cfg


def _apply_env(cfg: Config) -> None:
    """Secrets and per-machine overrides belong in the environment, not YAML."""
    env = os.environ
    if env.get("TARGET_API_KEY"):
        cfg.api_key = env["TARGET_API_KEY"]
    if env.get("POKEMON_TCINS"):
        cfg.products = _parse_products(
            [t for t in env["POKEMON_TCINS"].replace(",", " ").split() if t]
        )
    if env.get("POKEMON_STORE_IDS"):
        cfg.store_ids = [
            s for s in env["POKEMON_STORE_IDS"].replace(",", " ").split() if s
        ]
    if env.get("POKEMON_INTERVAL_SECONDS"):
        cfg.interval_seconds = int(env["POKEMON_INTERVAL_SECONDS"])
    if env.get("POKEMON_STATE_FILE"):
        cfg.state_file = Path(env["POKEMON_STATE_FILE"])

    if env.get("POKEMON_WEBHOOK_URL"):
        cfg.notify.webhook.url = env["POKEMON_WEBHOOK_URL"]
        cfg.notify.webhook.enabled = True
    if env.get("POKEMON_DESKTOP_NOTIFY"):
        cfg.notify.desktop = _as_bool(env["POKEMON_DESKTOP_NOTIFY"])

    if env.get("POKEMON_SMTP_USERNAME"):
        cfg.notify.email.username = env["POKEMON_SMTP_USERNAME"]
        cfg.notify.email.sender = cfg.notify.email.sender or env["POKEMON_SMTP_USERNAME"]
    if env.get("POKEMON_SMTP_PASSWORD"):
        cfg.notify.email.password = env["POKEMON_SMTP_PASSWORD"]
    if env.get("POKEMON_SMTP_HOST"):
        cfg.notify.email.host = env["POKEMON_SMTP_HOST"]
    if env.get("POKEMON_SMTP_PORT"):
        cfg.notify.email.port = int(env["POKEMON_SMTP_PORT"])
    if env.get("POKEMON_EMAIL_TO"):
        cfg.notify.email.recipients = [
            r.strip() for r in env["POKEMON_EMAIL_TO"].split(",") if r.strip()
        ]
    if cfg.notify.email.username and cfg.notify.email.recipients:
        cfg.notify.email.enabled = True
