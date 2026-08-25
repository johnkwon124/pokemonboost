"""Thin client over Target's RedSky aggregation API (the JSON API target.com
itself calls from the browser).

Only read-only endpoints are used: product fulfillment, product summary,
keyword search and nearby-store lookup.
"""

from __future__ import annotations

import html
import logging
import random
import re
import time
import uuid
from dataclasses import dataclass

import requests

from pokemon_stock.config import Config
from pokemon_stock.models import ProductStock, StoreStock, parse_availability

log = logging.getLogger(__name__)

BASE = "https://redsky.target.com/redsky_aggregations/v1/web"
FULFILLMENT_URL = f"{BASE}/pdp_fulfillment_v1"
PRODUCT_URL = f"{BASE}/pdp_client_v1"
SEARCH_URL = f"{BASE}/plp_search_v2"
NEARBY_STORES_URL = f"{BASE}/nearby_stores_v1"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class TargetApiError(RuntimeError):
    """RedSky returned something we cannot use."""


def _brief(error: Exception) -> str:
    """Transport errors embed the full request URL — which carries the API key.
    Strip query strings before logging and keep the message short."""
    text = " ".join(str(error).split())
    text = re.sub(r"\?[^\s'\"),]+", "", text)
    return text if len(text) <= 200 else text[:197] + "..."


@dataclass(frozen=True)
class SearchHit:
    tcin: str
    title: str
    price: str | None
    url: str


def product_url(tcin: str) -> str:
    return f"https://www.target.com/p/A-{tcin}"


class TargetClient:
    def __init__(self, config: Config, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.target.com",
                "Referer": "https://www.target.com/",
            }
        )
        self.visitor_id = uuid.uuid4().hex.upper()
        self._title_cache: dict[str, tuple[str, str | None]] = {}

    # ---------------------------------------------------------------- http

    def _get(self, url: str, params: dict) -> dict:
        """GET with retries on throttling, 5xx and transport errors."""
        params = {"key": self.config.api_key, **params}
        last_error: Exception | None = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self.session.get(
                    url, params=params, timeout=self.config.request_timeout
                )
            except requests.RequestException as exc:
                last_error = exc
                log.warning("요청 실패 (%s/%s): %s", attempt, self.config.max_retries, _brief(exc))
            else:
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise TargetApiError(f"JSON 파싱 실패: {url}") from exc
                if response.status_code in (401, 403):
                    raise TargetApiError(
                        f"RedSky가 {response.status_code}를 반환했습니다. "
                        "API key가 만료되었을 수 있습니다 (TARGET_API_KEY 환경변수로 교체)."
                    )
                if response.status_code == 404:
                    raise TargetApiError(f"존재하지 않는 리소스입니다 (404): {params.get('tcin', url)}")
                last_error = TargetApiError(f"HTTP {response.status_code}")
                log.warning(
                    "HTTP %s (%s/%s) — 재시도합니다.",
                    response.status_code,
                    attempt,
                    self.config.max_retries,
                )

            if attempt < self.config.max_retries:
                backoff = min(2 ** attempt, 30) + random.uniform(0, 1.5)
                time.sleep(backoff)

        raise TargetApiError(
            f"{self.config.max_retries}회 재시도 후에도 실패했습니다: "
            f"{_brief(last_error) if last_error else '원인 불명'}"
        )

    # ----------------------------------------------------------- endpoints

    def fetch_stock(self, tcin: str) -> ProductStock:
        """Fulfillment status for one product, across shipping and pickup."""
        store_id = self.config.primary_store_id
        payload = self._get(
            FULFILLMENT_URL,
            {
                "tcin": tcin,
                "is_bot": "false",
                "store_id": store_id,
                "pricing_store_id": store_id,
                "scheduled_delivery_store_id": store_id,
                "required_store_id": store_id,
                "has_required_store_id": "true",
                "zip": self.config.zip_code,
                "state": self.config.state,
                "latitude": f"{self.config.latitude:.2f}",
                "longitude": f"{self.config.longitude:.2f}",
                "visitor_id": self.visitor_id,
                "channel": "WEB",
                "page": f"/p/A-{tcin}",
            },
        )
        title, price = self._describe(tcin)
        return parse_fulfillment(payload, tcin, title, price, self.config.store_ids)

    def _describe(self, tcin: str) -> tuple[str, str | None]:
        """Title and price, cached — they do not change between polls."""
        if tcin in self._title_cache:
            return self._title_cache[tcin]
        try:
            payload = self._get(
                PRODUCT_URL,
                {
                    "tcin": tcin,
                    "is_bot": "false",
                    "store_id": self.config.primary_store_id,
                    "pricing_store_id": self.config.primary_store_id,
                    "has_pricing_store_id": "true",
                    "visitor_id": self.visitor_id,
                    "channel": "WEB",
                    "page": f"/p/A-{tcin}",
                },
            )
            described = parse_product_summary(payload, tcin)
        except TargetApiError as exc:
            # A missing title must never stop a stock check.
            log.debug("상품 정보 조회 실패 (%s): %s", tcin, exc)
            described = (f"TCIN {tcin}", None)
        self._title_cache[tcin] = described
        return described

    def search(self, keyword: str, limit: int = 24) -> list[SearchHit]:
        payload = self._get(
            SEARCH_URL,
            {
                "keyword": keyword,
                "channel": "WEB",
                "count": str(limit),
                "offset": "0",
                "page": f"/s/{keyword}",
                "platform": "desktop",
                "pricing_store_id": self.config.primary_store_id,
                "store_ids": self.config.primary_store_id,
                "visitor_id": self.visitor_id,
                "zip": self.config.zip_code,
                "state": self.config.state,
                "latitude": f"{self.config.latitude:.2f}",
                "longitude": f"{self.config.longitude:.2f}",
                "default_purchasability_filter": "true",
                "include_sponsored": "false",
            },
        )
        return parse_search(payload)

    def nearby_stores(self, place: str, limit: int = 10, within: int = 50) -> list[dict]:
        payload = self._get(
            NEARBY_STORES_URL,
            {
                "place": place,
                "limit": str(limit),
                "within": str(within),
                "visitor_id": self.visitor_id,
            },
        )
        stores = (payload.get("data") or {}).get("nearby_stores") or {}
        results = []
        for store in stores.get("stores") or []:
            address = store.get("mailing_address") or {}
            results.append(
                {
                    "store_id": str(store.get("store_id", "")),
                    "name": store.get("location_name", ""),
                    "city": address.get("city", ""),
                    "state": address.get("region", ""),
                    "distance": store.get("distance"),
                }
            )
        return results


# ------------------------------------------------------------------ parsing
# Parsing is kept as free functions so it can be tested against saved
# fixtures without touching the network.


def parse_fulfillment(
    payload: dict,
    tcin: str,
    title: str,
    price: str | None,
    watched_store_ids: list[str],
) -> ProductStock:
    product = (payload.get("data") or {}).get("product") or {}
    fulfillment = product.get("fulfillment") or {}
    if not fulfillment:
        raise TargetApiError(f"응답에 fulfillment 정보가 없습니다 (tcin={tcin})")

    shipping_raw = (fulfillment.get("shipping_options") or {}).get("availability_status")

    watched = {str(s) for s in watched_store_ids}
    stores: list[StoreStock] = []
    for option in fulfillment.get("store_options") or []:
        store_id = str(option.get("location_id") or option.get("store_id") or "")
        if watched and store_id not in watched:
            continue
        pickup = option.get("order_pickup") or {}
        in_store = option.get("in_store_only") or {}
        status = pickup.get("availability_status") or in_store.get("availability_status")
        stores.append(
            StoreStock(
                store_id=store_id,
                store_name=option.get("location_name") or store_id,
                availability=parse_availability(status),
                quantity=option.get("location_available_to_promise_quantity"),
            )
        )

    missing = watched - {s.store_id for s in stores}
    if missing:
        log.warning(
            "매장 %s는 응답에 없습니다 (거리가 멀거나 취급하지 않는 상품). "
            "location의 zip/위경도를 해당 매장 근처로 맞추세요.",
            ", ".join(sorted(missing)),
        )

    return ProductStock(
        tcin=tcin,
        title=title,
        url=product_url(tcin),
        price=price,
        shipping=parse_availability(shipping_raw),
        stores=stores,
        raw_shipping_status=shipping_raw,
    )


def parse_product_summary(payload: dict, tcin: str) -> tuple[str, str | None]:
    product = (payload.get("data") or {}).get("product") or {}
    item = product.get("item") or {}
    description = item.get("product_description") or {}
    title = description.get("title") or f"TCIN {tcin}"
    price = (product.get("price") or {}).get("formatted_current_price")
    return _unescape(title), price


def parse_search(payload: dict) -> list[SearchHit]:
    search = (payload.get("data") or {}).get("search") or {}
    hits: list[SearchHit] = []
    for product in search.get("products") or []:
        tcin = str(product.get("tcin", ""))
        if not tcin:
            continue
        description = (product.get("item") or {}).get("product_description") or {}
        hits.append(
            SearchHit(
                tcin=tcin,
                title=_unescape(description.get("title") or f"TCIN {tcin}"),
                price=(product.get("price") or {}).get("formatted_current_price"),
                url=product_url(tcin),
            )
        )
    return hits


def _unescape(title: str) -> str:
    """RedSky titles arrive with HTML entities and stray markup."""
    return re.sub(r"<[^>]+>", "", html.unescape(title)).strip()
