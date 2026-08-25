import pytest

from pokemon_stock.models import Availability, Channel, parse_availability
from pokemon_stock.target_client import (
    TargetApiError,
    parse_fulfillment,
    parse_product_summary,
    parse_search,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("IN_STOCK", Availability.IN_STOCK),
        ("in_stock", Availability.IN_STOCK),
        ("LIMITED_STOCK", Availability.LIMITED),
        ("PRE_ORDER_SELLABLE", Availability.PREORDER),
        ("PRE_ORDER_UNSELLABLE", Availability.OUT_OF_STOCK),
        ("OUT_OF_STOCK", Availability.OUT_OF_STOCK),
        ("NOT_SOLD_IN_STORE", Availability.UNAVAILABLE),
        ("SOMETHING_NEW", Availability.UNKNOWN),
        (None, Availability.UNKNOWN),
    ],
)
def test_parse_availability(raw, expected):
    assert parse_availability(raw) is expected


def test_unknown_status_is_not_buyable():
    assert not Availability.UNKNOWN.is_buyable
    assert Availability.PREORDER.is_buyable


def test_parse_fulfillment_in_stock_filters_to_watched_stores(fixture):
    stock = parse_fulfillment(
        fixture("fulfillment_in_stock.json"), "94300072", "Booster Bundle", "$26.99", ["1234", "5678"]
    )
    assert stock.shipping is Availability.IN_STOCK
    assert [s.store_id for s in stock.stores] == ["1234", "5678"]  # 9999 is not watched
    assert stock.pickup is Availability.IN_STOCK
    assert [s.store_id for s in stock.pickup_stores_in_stock()] == ["1234"]
    assert stock.url == "https://www.target.com/p/A-94300072"
    assert stock.is_buyable([Channel.SHIPPING, Channel.PICKUP])


def test_parse_fulfillment_keeps_all_stores_when_none_watched(fixture):
    stock = parse_fulfillment(fixture("fulfillment_in_stock.json"), "94300072", "t", None, [])
    assert len(stock.stores) == 3


def test_parse_fulfillment_out_of_stock(fixture):
    stock = parse_fulfillment(
        fixture("fulfillment_out_of_stock.json"), "94300072", "t", None, ["1234"]
    )
    assert stock.shipping is Availability.OUT_OF_STOCK
    assert stock.pickup is Availability.OUT_OF_STOCK
    assert not stock.is_buyable([Channel.SHIPPING, Channel.PICKUP])


def test_preorder_counts_as_buyable_and_has_no_stores(fixture):
    stock = parse_fulfillment(fixture("fulfillment_preorder.json"), "88888888", "t", None, [])
    assert stock.shipping is Availability.PREORDER
    assert stock.pickup is Availability.UNKNOWN
    assert stock.is_buyable([Channel.SHIPPING])
    assert not stock.is_buyable([Channel.PICKUP])


def test_parse_fulfillment_rejects_payload_without_fulfillment():
    with pytest.raises(TargetApiError):
        parse_fulfillment({"data": {"product": {}}}, "1", "t", None, [])


def test_parse_product_summary_unescapes_title(fixture):
    title, price = parse_product_summary(fixture("product_summary.json"), "94300072")
    assert title == "Pokémon Trading Card Game: Scarlet & Violet Booster Bundle"
    assert price == "$26.99"


def test_parse_product_summary_falls_back_to_tcin():
    assert parse_product_summary({}, "42") == ("TCIN 42", None)


def test_parse_search_skips_entries_without_tcin(fixture):
    hits = parse_search(fixture("search.json"))
    assert [h.tcin for h in hits] == ["94300072", "89757321"]
    assert hits[0].title == "Pokémon TCG: Booster Bundle"
    assert hits[1].url == "https://www.target.com/p/A-89757321"


def test_summary_mentions_in_stock_pickup_store(fixture):
    stock = parse_fulfillment(
        fixture("fulfillment_in_stock.json"), "94300072", "t", None, ["1234", "5678"]
    )
    summary = stock.summary([Channel.SHIPPING, Channel.PICKUP])
    assert "배송 IN_STOCK" in summary
    assert "Palo Alto(1234)" in summary
    assert "San Jose" not in summary


def test_brief_error_hides_api_key_and_truncates():
    import requests

    from pokemon_stock.target_client import _brief

    error = requests.exceptions.ProxyError(
        "HTTPSConnectionPool(host='redsky.target.com', port=443): Max retries exceeded "
        "with url: /redsky_aggregations/v1/web/pdp_fulfillment_v1?key=SECRETKEY&tcin=1 "
        "(Caused by ProxyError('Unable to connect to proxy'))"
    )
    brief = _brief(error)
    assert "SECRETKEY" not in brief
    assert "pdp_fulfillment_v1" in brief
    assert len(brief) <= 200


def test_missing_watched_store_is_warned_and_not_treated_as_stock(fixture, caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        stock = parse_fulfillment(
            fixture("fulfillment_in_stock.json"), "94300072", "t", None, ["1234", "7777"]
        )
    assert "7777" in caplog.text
    assert [s.store_id for s in stock.stores] == ["1234"]


def test_no_matching_store_means_pickup_is_unknown(fixture):
    stock = parse_fulfillment(fixture("fulfillment_in_stock.json"), "94300072", "t", None, ["7777"])
    assert stock.stores == []
    assert stock.pickup is Availability.UNKNOWN
    assert not stock.is_buyable([Channel.PICKUP])
