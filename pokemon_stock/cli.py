"""Command line interface for the Target Pokémon TCG stock monitor."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from pokemon_stock.config import Config, ConfigError, WatchItem, load_config
from pokemon_stock.models import Availability, Channel
from pokemon_stock.monitor import Monitor
from pokemon_stock.notifiers import Alert, build_notifiers, dispatch
from pokemon_stock.target_client import TargetApiError, TargetClient, product_url

DEFAULT_CONFIG = Path("config.yaml")
EXAMPLE_CONFIG = Path(__file__).resolve().parent.parent / "config.example.yaml"

log = logging.getLogger("pokemon_stock")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


def _resolve_config(path: str | None) -> Config:
    chosen = Path(path) if path else (DEFAULT_CONFIG if DEFAULT_CONFIG.exists() else None)
    config = load_config(chosen)
    if chosen:
        log.debug("설정 파일 사용: %s", chosen)
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pokemon-stock",
        description="Target.com 포켓몬 TCG 상품의 재입고를 주기적으로 감시합니다.",
    )
    parser.add_argument("-c", "--config", help="설정 YAML 경로 (기본: ./config.yaml)")
    parser.add_argument("-v", "--verbose", action="store_true", help="디버그 로그 출력")
    sub = parser.add_subparsers(dest="command", required=True)

    watch = sub.add_parser("watch", help="주기적으로 감시하며 재입고 시 알림")
    watch.add_argument("--once", action="store_true", help="한 번만 확인하고 종료 (cron용)")
    watch.add_argument("--interval", type=int, help="확인 주기(초) 오버라이드")
    watch.add_argument("--cycles", type=int, help="지정한 횟수만큼만 반복")

    check = sub.add_parser("check", help="지금 재고 상태를 한 번 출력 (상태 파일/알림 미사용)")
    check.add_argument("tcins", nargs="*", help="확인할 TCIN (생략 시 설정의 products)")

    search = sub.add_parser("search", help="키워드로 상품을 찾아 TCIN 확인")
    search.add_argument("keyword", nargs="+", help="검색어 (예: pokemon booster bundle)")
    search.add_argument("--limit", type=int, default=24, help="최대 결과 수 (기본 24)")

    stores = sub.add_parser("stores", help="우편번호 근처 매장의 store_id 조회")
    stores.add_argument("place", help="우편번호 또는 도시 (예: 94301)")
    stores.add_argument("--limit", type=int, default=10)

    sub.add_parser("notify-test", help="설정된 모든 알림 채널로 테스트 알림 발송")
    init = sub.add_parser("init", help="config.example.yaml을 config.yaml로 복사")
    init.add_argument("--force", action="store_true", help="기존 config.yaml 덮어쓰기")
    return parser


# --------------------------------------------------------------- commands


def cmd_watch(args: argparse.Namespace, config: Config) -> int:
    if args.interval:
        config.interval_seconds = args.interval
    config.validate()
    monitor = Monitor(config)
    cycles = 1 if args.once else args.cycles
    monitor.run(max_cycles=cycles)
    return 0


def _status_icon(buyable: bool) -> str:
    return "🟢" if buyable else "🔴"


def cmd_check(args: argparse.Namespace, config: Config) -> int:
    items = (
        [WatchItem(tcin=t) for t in args.tcins]
        if args.tcins
        else config.products
    )
    if not items:
        raise ConfigError("확인할 TCIN이 없습니다. 인자로 넘기거나 config의 products를 채우세요.")

    client = TargetClient(config)
    failures = 0
    for item in items:
        try:
            stock = client.fetch_stock(item.tcin)
        except TargetApiError as exc:
            failures += 1
            print(f"❌ {item.display()} — {exc}")
            continue

        print(f"{_status_icon(stock.is_buyable(config.channels))} {item.display(stock.title)}")
        print(f"   배송  : {stock.shipping.value}")
        if Channel.PICKUP in config.channels or stock.stores:
            for store in stock.stores:
                quantity = f" (재고 {int(store.quantity)})" if store.quantity else ""
                print(
                    f"   픽업  : {_status_icon(store.availability.is_buyable)} "
                    f"{store.store_name}({store.store_id}) {store.availability.value}{quantity}"
                )
        if stock.price:
            print(f"   가격  : {stock.price}")
        print(f"   링크  : {stock.url}")
    return 1 if failures == len(items) else 0


def cmd_search(args: argparse.Namespace, config: Config) -> int:
    keyword = " ".join(args.keyword)
    client = TargetClient(config)
    hits = client.search(keyword, limit=args.limit)
    if not hits:
        print(f"'{keyword}' 검색 결과가 없습니다.")
        return 0
    print(f"'{keyword}' 검색 결과 {len(hits)}건 — config.yaml의 products에 tcin을 넣으세요.\n")
    for hit in hits:
        price = f"  {hit.price}" if hit.price else ""
        print(f"  {hit.tcin}  {hit.title[:70]}{price}")
        print(f"          {hit.url}")
    return 0


def cmd_stores(args: argparse.Namespace, config: Config) -> int:
    client = TargetClient(config)
    stores = client.nearby_stores(args.place, limit=args.limit)
    if not stores:
        print(f"'{args.place}' 근처 매장을 찾지 못했습니다.")
        return 0
    print(f"'{args.place}' 근처 매장 — config.yaml의 store_ids에 넣으세요.\n")
    for store in stores:
        distance = f"  {store['distance']}mi" if store.get("distance") is not None else ""
        print(f"  {store['store_id']}  {store['name']} ({store['city']}, {store['state']}){distance}")
    return 0


def cmd_notify_test(_: argparse.Namespace, config: Config) -> int:
    from pokemon_stock.models import ProductStock

    notifiers = build_notifiers(config)
    if not notifiers:
        print("설정된 알림 채널이 없습니다. config.yaml의 notify 섹션을 확인하세요.")
        return 1

    sample = ProductStock(
        tcin="00000000",
        title="[테스트] Pokémon TCG Booster Bundle",
        url=product_url("00000000"),
        price="$26.99",
        shipping=Availability.IN_STOCK,
    )
    dispatch(notifiers, Alert(stock=sample, channels=config.channels, label=sample.title))
    print(f"테스트 알림을 {len(notifiers)}개 채널로 발송했습니다: "
          f"{', '.join(n.name for n in notifiers)}")
    return 0


def cmd_init(args: argparse.Namespace, _: Config) -> int:
    if DEFAULT_CONFIG.exists() and not args.force:
        print(f"{DEFAULT_CONFIG}가 이미 있습니다. 덮어쓰려면 --force를 쓰세요.")
        return 1
    shutil.copyfile(EXAMPLE_CONFIG, DEFAULT_CONFIG)
    print(f"{DEFAULT_CONFIG} 생성 완료. products/store_ids를 채운 뒤 watch를 실행하세요.")
    return 0


COMMANDS = {
    "watch": cmd_watch,
    "check": cmd_check,
    "search": cmd_search,
    "stores": cmd_stores,
    "notify-test": cmd_notify_test,
    "init": cmd_init,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    try:
        config = _resolve_config(args.config)
        return COMMANDS[args.command](args, config)
    except ConfigError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 2
    except TargetApiError as exc:
        print(f"Target API 오류: {exc}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        return 130
