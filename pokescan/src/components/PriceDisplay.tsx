"use client";

import { useEffect, useState } from "react";
import type { Card, MarketPrice } from "@/types/card";
import { pickGeneralPrice } from "@/lib/tcg";
import { eurToUsdRate, FALLBACK_EUR_USD } from "@/lib/fx";

function fmt(n: number | null): string {
  if (n === null) return "—";
  if (n < 100) return `$${n.toFixed(2)}`;
  return `$${Math.round(n).toLocaleString()}`;
}

function variantLabel(variant: MarketPrice["variant"]): string {
  switch (variant) {
    case "normal":
      return "노멀";
    case "holofoil":
      return "홀로";
    case "reverseHolofoil":
      return "리버스홀로";
    case "1stEditionNormal":
      return "1st 에디션";
    case "1stEditionHolofoil":
      return "1st 에디션 홀로";
    default:
      return variant;
  }
}

function hasAnyNumber(p: MarketPrice | null): boolean {
  return !!p && (p.marketUsd !== null || p.lowUsd !== null || p.midUsd !== null || p.highUsd !== null);
}

/** One-tap cross-check links so a missing/odd number never dead-ends the user. */
function MarketLinks({ card }: { card: Card }) {
  const q = encodeURIComponent(
    `pokemon ${card.name} ${card.number}${card.setPrintedTotal ? `/${card.setPrintedTotal}` : ""}`
  );
  const tq = encodeURIComponent(card.name);
  return (
    <div className="mt-3 flex gap-2">
      <a
        href={`https://www.ebay.com/sch/i.html?_nkw=${q}&LH_Sold=1&LH_Complete=1`}
        target="_blank"
        rel="noreferrer"
        className="flex-1 rounded-lg border border-ink-600 py-1.5 text-center text-[11px] font-medium text-ink-100 active:scale-95"
      >
        eBay 실거래가 보기
      </a>
      <a
        href={`https://www.tcgplayer.com/search/pokemon/product?q=${tq}`}
        target="_blank"
        rel="noreferrer"
        className="flex-1 rounded-lg border border-ink-600 py-1.5 text-center text-[11px] font-medium text-ink-100 active:scale-95"
      >
        TCGPlayer 검색
      </a>
    </div>
  );
}

export default function PriceDisplay({ card }: { card: Card }) {
  const [eurUsd, setEurUsd] = useState(FALLBACK_EUR_USD);
  const cm = card.cardmarket;
  useEffect(() => {
    if (cm) eurToUsdRate().then(setEurUsd);
  }, [cm]);

  const headline = pickGeneralPrice(card);

  // 1) Primary: TCGPlayer (US) prices
  if (hasAnyNumber(headline)) {
    const h = headline!;
    return (
      <section className="rounded-2xl border border-ink-700 bg-ink-900 p-4">
        <div className="flex items-baseline justify-between">
          <p className="text-xs uppercase tracking-wider text-ink-400">현재 시장가 (raw NM)</p>
          {card.estimated && (
            <span className="rounded-full bg-ink-700 px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-200">추정치</span>
          )}
        </div>
        <p className="mt-1 text-4xl font-semibold tracking-tight text-ink-100">{fmt(h.marketUsd ?? h.midUsd)}</p>
        <p className="mt-1 text-xs text-ink-400">
          {variantLabel(h.variant)} · TCGPlayer
          {h.updatedAt && ` · ${new Date(h.updatedAt).toLocaleDateString("ko-KR")}`}
        </p>

        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Stat label="저가" value={fmt(h.lowUsd)} />
          <Stat label="중간" value={fmt(h.midUsd)} />
          <Stat label="고가" value={fmt(h.highUsd)} />
        </div>

        {card.prices.length > 1 && (
          <details className="mt-3 text-xs text-ink-300">
            <summary className="cursor-pointer text-ink-400">다른 버전 시세</summary>
            <ul className="mt-2 space-y-1">
              {card.prices
                .filter((p) => p.variant !== h.variant)
                .map((p) => (
                  <li key={p.variant} className="flex justify-between">
                    <span>{variantLabel(p.variant)}</span>
                    <span className="text-ink-100">{fmt(p.marketUsd)}</span>
                  </li>
                ))}
            </ul>
          </details>
        )}

        <p className="mt-3 text-[11px] leading-relaxed text-ink-400">
          {card.estimated
            ? "동일 카드 영문판의 raw NM 시세입니다. 일본어/한국어판 실거래가와 다를 수 있습니다."
            : "그레이딩(PSA 10)이 아닌 일반 거래(raw, NM) 시세. TCGPlayer 마켓가 기준."}
        </p>
        <MarketLinks card={card} />
      </section>
    );
  }

  // 2) Fallback: Cardmarket (EU) prices — often present when TCGPlayer sync lags
  if (cm && (cm.trendEur !== null || cm.avgSellEur !== null)) {
    const mainEur = cm.trendEur ?? cm.avgSellEur!;
    return (
      <section className="rounded-2xl border border-ink-700 bg-ink-900 p-4">
        <div className="flex items-baseline justify-between">
          <p className="text-xs uppercase tracking-wider text-ink-400">현재 시장가 (raw NM)</p>
          <span className="rounded-full bg-ink-700 px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-200">
            Cardmarket
          </span>
        </div>
        <p className="mt-1 text-4xl font-semibold tracking-tight text-ink-100">≈{fmt(mainEur * eurUsd)}</p>
        <p className="mt-1 text-xs text-ink-400">
          €{mainEur.toFixed(2)} · Cardmarket(유럽) 트렌드가 환산
          {cm.updatedAt && ` · ${new Date(cm.updatedAt).toLocaleDateString("ko-KR")}`}
        </p>

        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Stat label="저가" value={cm.lowEur !== null ? `≈${fmt(cm.lowEur * eurUsd)}` : "—"} />
          <Stat label="30일 평균" value={cm.avg30Eur !== null ? `≈${fmt(cm.avg30Eur * eurUsd)}` : "—"} />
          <Stat label="평균 판매" value={cm.avgSellEur !== null ? `≈${fmt(cm.avgSellEur * eurUsd)}` : "—"} />
        </div>

        <p className="mt-3 text-[11px] leading-relaxed text-ink-400">
          미국(TCGPlayer) 시세가 아직 집계되지 않아 유럽 Cardmarket 시세를 USD로 환산해 보여줍니다. 미국 실거래가와
          다소 차이가 있을 수 있어요.
        </p>
        <MarketLinks card={card} />
      </section>
    );
  }

  // 3) Nothing from either source — say why, and hand the user a way to check
  return (
    <section className="rounded-2xl border border-ink-700 bg-ink-900 p-4">
      <p className="text-xs uppercase tracking-wider text-ink-400">시장 가치</p>
      <p className="mt-2 text-sm leading-relaxed text-ink-300">
        이 카드는 카드 자체가 없는 게 아니라, 무료 시세 데이터 공급(TCGPlayer·Cardmarket 동기화)이 아직 이 카드의
        가격을 제공하지 않는 상태입니다. 트레이너 카드와 최신 세트에서 종종 발생해요.
      </p>
      <p className="mt-2 text-[11px] text-ink-400">아래 버튼으로 실제 거래가를 바로 확인할 수 있습니다.</p>
      <MarketLinks card={card} />
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-ink-800 px-2 py-2">
      <p className="text-[10px] uppercase tracking-wider text-ink-400">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-ink-100">{value}</p>
    </div>
  );
}
