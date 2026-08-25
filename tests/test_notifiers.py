import pytest

from pokemon_stock.config import WebhookConfig
from pokemon_stock.models import Availability, Channel, ProductStock, StoreStock
from pokemon_stock.notifiers import build_notifiers
from pokemon_stock.notifiers.base import Alert
from pokemon_stock.notifiers.webhook import WebhookNotifier
from pokemon_stock.config import Config


class FakeResponse:
    status_code = 204
    text = ""


class FakeSession:
    def __init__(self):
        self.posts = []

    def post(self, url, json=None, timeout=None):
        self.posts.append((url, json))
        return FakeResponse()


def make_alert() -> Alert:
    stock = ProductStock(
        tcin="94300072",
        title="Booster Bundle",
        url="https://www.target.com/p/A-94300072",
        price="$26.99",
        shipping=Availability.IN_STOCK,
        stores=[StoreStock("1234", "Palo Alto", Availability.IN_STOCK)],
    )
    return Alert(stock=stock, channels=[Channel.SHIPPING, Channel.PICKUP], label="번들")


@pytest.mark.parametrize(
    "url,expected_key",
    [
        ("https://discord.com/api/webhooks/1/abc", "content"),
        ("https://hooks.slack.com/services/T/B/x", "text"),
    ],
)
def test_webhook_uses_the_field_the_service_expects(url, expected_key):
    session = FakeSession()
    WebhookNotifier(WebhookConfig(enabled=True, url=url), session=session).send(make_alert())
    posted_url, body = session.posts[0]
    assert posted_url == url
    assert list(body) == [expected_key]
    assert "번들" in body[expected_key]
    assert "https://www.target.com/p/A-94300072" in body[expected_key]


def test_webhook_failure_is_swallowed():
    import requests

    class BrokenSession:
        def post(self, *args, **kwargs):
            raise requests.RequestException("연결 실패")

    notifier = WebhookNotifier(WebhookConfig(enabled=True, url="https://x.test"), session=BrokenSession())
    notifier.send(make_alert())  # must not raise


def test_alert_body_lists_the_in_stock_pickup_store():
    body = make_alert().body
    assert "Palo Alto(1234)" in body
    assert "$26.99" in body


def test_build_notifiers_respects_config():
    config = Config()
    assert [n.name for n in build_notifiers(config)] == ["console"]

    config.notify.desktop = True
    config.notify.webhook.enabled = True
    config.notify.webhook.url = "https://discord.com/api/webhooks/1/abc"
    config.notify.email.enabled = True
    config.notify.email.recipients = ["me@example.test"]
    assert [n.name for n in build_notifiers(config)] == ["console", "desktop", "webhook", "email"]


def test_webhook_without_url_is_not_built():
    config = Config()
    config.notify.webhook.enabled = True
    config.notify.webhook.url = ""
    assert [n.name for n in build_notifiers(config)] == ["console"]
