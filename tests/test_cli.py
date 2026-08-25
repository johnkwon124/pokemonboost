import pytest

from pokemon_stock import cli
from pokemon_stock.config import Config
from pokemon_stock.models import Availability, ProductStock
from pokemon_stock.target_client import SearchHit, TargetApiError


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (
        "POKEMON_TCINS",
        "POKEMON_STORE_IDS",
        "POKEMON_WEBHOOK_URL",
        "POKEMON_SMTP_USERNAME",
        "POKEMON_EMAIL_TO",
        "POKEMON_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)


class StubClient:
    def __init__(self, config, **_):
        self.config = config

    def fetch_stock(self, tcin: str) -> ProductStock:
        if tcin == "99999999":
            raise TargetApiError("존재하지 않는 리소스입니다 (404)")
        return ProductStock(
            tcin=tcin,
            title="Booster Bundle",
            url=f"https://www.target.com/p/A-{tcin}",
            price="$26.99",
            shipping=Availability.IN_STOCK,
        )

    def search(self, keyword, limit=24):
        return [SearchHit("94300072", "Booster Bundle", "$26.99", "https://www.target.com/p/A-94300072")]

    def nearby_stores(self, place, limit=10, within=50):
        return [{"store_id": "1234", "name": "Palo Alto", "city": "Palo Alto", "state": "CA", "distance": 2.1}]


@pytest.fixture
def stub_client(monkeypatch):
    monkeypatch.setattr(cli, "TargetClient", StubClient)


def test_check_prints_status(stub_client, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_resolve_config", lambda _: Config())
    assert cli.main(["check", "94300072"]) == 0
    out = capsys.readouterr().out
    assert "🟢" in out
    assert "IN_STOCK" in out
    assert "https://www.target.com/p/A-94300072" in out


def test_check_reports_failure_and_exits_nonzero(stub_client, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_resolve_config", lambda _: Config())
    assert cli.main(["check", "99999999"]) == 1
    assert "❌" in capsys.readouterr().out


def test_check_without_tcins_or_config_is_a_config_error(stub_client, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_resolve_config", lambda _: Config())
    assert cli.main(["check"]) == 2
    assert "설정 오류" in capsys.readouterr().err


def test_search_lists_tcins(stub_client, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_resolve_config", lambda _: Config())
    assert cli.main(["search", "pokemon", "booster"]) == 0
    assert "94300072" in capsys.readouterr().out


def test_stores_lists_store_ids(stub_client, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_resolve_config", lambda _: Config())
    assert cli.main(["stores", "94301"]) == 0
    assert "1234  Palo Alto" in capsys.readouterr().out


def test_notify_test_without_channels_fails(capsys, monkeypatch):
    config = Config()
    config.notify.console = False
    monkeypatch.setattr(cli, "_resolve_config", lambda _: config)
    assert cli.main(["notify-test"]) == 1


def test_notify_test_uses_console_channel(capsys, monkeypatch):
    monkeypatch.setattr(cli, "_resolve_config", lambda _: Config())
    assert cli.main(["notify-test"]) == 0
    assert "테스트" in capsys.readouterr().out


def test_init_copies_example(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "DEFAULT_CONFIG", tmp_path / "config.yaml")
    assert cli.main(["init"]) == 0
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8").startswith("# Target.com")
    assert cli.main(["init"]) == 1  # refuses to clobber
    assert cli.main(["init", "--force"]) == 0


def test_watch_once_runs_a_single_cycle(stub_client, monkeypatch):
    calls = {"cycles": None}

    class StubMonitor:
        def __init__(self, config):
            self.config = config

        def run(self, max_cycles=None):
            calls["cycles"] = max_cycles
            return 1

    config = Config()
    config.products = cli.load_config("config.example.yaml").products
    monkeypatch.setattr(cli, "_resolve_config", lambda _: config)
    monkeypatch.setattr(cli, "Monitor", StubMonitor)
    assert cli.main(["watch", "--once"]) == 0
    assert calls["cycles"] == 1


def test_watch_interval_override(stub_client, monkeypatch):
    seen = {}

    class StubMonitor:
        def __init__(self, config):
            seen["interval"] = config.interval_seconds

        def run(self, max_cycles=None):
            return 0

    config = cli.load_config("config.example.yaml")
    monkeypatch.setattr(cli, "_resolve_config", lambda _: config)
    monkeypatch.setattr(cli, "Monitor", StubMonitor)
    assert cli.main(["watch", "--interval", "600", "--cycles", "2"]) == 0
    assert seen["interval"] == 600
