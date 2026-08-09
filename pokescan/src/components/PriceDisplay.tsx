import type { Card, MarketPrice } from "@/types/card";
import { pickGeneralPrice } from "@/lib/tcg";

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

export default function PriceDisplay({ card }: { card: Card }) {
  const headline = pickGeneralPrice(card);
  if (!headline) {
    return (
      <section className="rounded-2xl border border-ink-700 bg-ink-900 p-4">
        <p className="text-xs uppercase tracking-wider text-ink-400">시장 가치</p>
        <p className="mt-2 text-sm text-ink-300">시세 데이터가 없습니다.</p>
        {card.locale === "jp" && (
          <p className="mt-2 text-[11px] text-ink-400">일본어 카드는 별도 시세 소스가 부족합니다.</p>
        )}
        {card.locale === "kr" && (
          <p className="mt-2 text-[11px] text-ink-400">한국어 카드는 별도 시세 소스가 부족합니다.</p>
        )}
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-ink-700 bg-ink-900 p-4">
      <div className="flex items-baseline justify-between">
        <p className="text-xs uppercase tracking-wider text-ink-400">현재 시장가 (raw NM)</p>
        {card.estimated && (
          <span className="rounded-full bg-ink-700 px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-200">추정치</span>
        )}
      </div>
      <p className="mt-1 text-4xl font-semibold tracking-tight text-ink-100">{fmt(headline.marketUsd)}</p>
      <p className="mt-1 text-xs text-ink-400">
        {variantLabel(headline.variant)} · {headline.source}
        {headline.updatedAt && ` · ${new Date(headline.updatedAt).toLocaleDateString("ko-KR")}`}
      </p>

      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <Stat label="저가" value={fmt(headline.lowUsd)} />
        <Stat label="중간" value={fmt(headline.midUsd)} />
        <Stat label="고가" value={fmt(headline.highUsd)} />
      </div>

      {card.prices.length > 1 && (
        <details className="mt-3 text-xs text-ink-300">
          <summary className="cursor-pointer text-ink-400">다른 버전 시세</summary>
          <ul className="mt-2 space-y-1">
            {card.prices
              .filter((p) => p.variant !== headline.variant)
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
          : "그레이딩(PSA 10) 가격이 아닌 일반 거래(raw, NM) 시세를 보여줍니다. TCGPlayer 마켓가 기준."}
      </p>
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
