import pytest

from pokemon_stock.config import ConfigError, load_config
from pokemon_stock.models import Channel

EXAMPLE = "config.example.yaml"


def test_defaults_without_file(monkeypatch):
    monkeypatch.delenv("TARGET_API_KEY", raising=False)
    config = load_config(None)
    assert config.products == []
    assert config.channels == [Channel.SHIPPING]
    assert config.interval_seconds == 180


def test_loads_example_config():
    config = load_config(EXAMPLE)
    assert [p.tcin for p in config.products] == ["94300072", "89757321"]
    assert config.products[0].label.startswith("Pokémon")
    assert config.channels == [Channel.SHIPPING]
    assert config.notify.console is True
    config.validate()


def test_env_overrides_beat_file(monkeypatch):
    monkeypatch.setenv("POKEMON_TCINS", "11111111,22222222")
    monkeypatch.setenv("POKEMON_INTERVAL_SECONDS", "300")
    monkeypatch.setenv("TARGET_API_KEY", "envkey")
    monkeypatch.setenv("POKEMON_WEBHOOK_URL", "https://example.test/hook")
    config = load_config(EXAMPLE)
    assert [p.tcin for p in config.products] == ["11111111", "22222222"]
    assert config.interval_seconds == 300
    assert config.api_key == "envkey"
    assert config.notify.webhook.enabled is True


def test_email_enabled_by_env_pair(monkeypatch):
    monkeypatch.setenv("POKEMON_SMTP_USERNAME", "me@example.test")
    monkeypatch.setenv("POKEMON_SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("POKEMON_EMAIL_TO", "a@example.test, b@example.test")
    config = load_config(EXAMPLE)
    assert config.notify.email.enabled is True
    assert config.notify.email.sender == "me@example.test"
    assert config.notify.email.recipients == ["a@example.test", "b@example.test"]


def test_missing_file_is_an_error():
    with pytest.raises(ConfigError):
        load_config("no-such-config.yaml")


def test_non_numeric_tcin_rejected(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("products:\n  - tcin: A-1234\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="숫자"):
        load_config(path)


def test_unknown_channel_rejected(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("products: ['1']\nchannels: [teleport]\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="channel"):
        load_config(path)


@pytest.mark.parametrize(
    "yaml_text,message",
    [
        ("products: []\n", "products"),
        ("products: ['1']\nchannels: [pickup]\nstore_ids: []\n", "store_ids"),
        ("products: ['1']\npolling:\n  interval_seconds: 5\n", "interval_seconds"),
    ],
)
def test_validate_rejects_unusable_config(tmp_path, yaml_text, message, monkeypatch):
    monkeypatch.delenv("POKEMON_TCINS", raising=False)
    monkeypatch.delenv("POKEMON_STORE_IDS", raising=False)
    monkeypatch.delenv("POKEMON_INTERVAL_SECONDS", raising=False)
    path = tmp_path / "c.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_config(path).validate()
