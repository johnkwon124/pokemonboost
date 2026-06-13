"use client";

import Image from "next/image";
import type { Analysis, Card, SessionScan } from "@/types/card";
import { pickGeneralPrice } from "@/lib/tcg";
import PriceDisplay from "./PriceDisplay";

interface Props {
  card: Card;
  analysis: Analysis | null;
  session: SessionScan[];
  onBack: () => void;
  onPickSession: (s: SessionScan) => void;
}

export default function CardResult({ card, analysis, session, onBack, onPickSession }: Props) {
  return (
    <div className="flex flex-col gap-4 px-4 pb-8">
      <div className="flex justify-end">
        <span className="text-[11px] text-ink-500">저장 안 됨 · 닫으면 사라짐</span>
      </div>

      {session.length > 1 && (
        <section>
          <p className="px-1 text-[11px] uppercase tracking-wider text-ink-500">이번 세션 ({session.length})</p>
          <div className="no-scrollbar mt-2 flex gap-2 overflow-x-auto pb-1">
            {session.map((s) => {
              const p = pickGeneralPrice(s.card);
              const active = s.card.id === card.id;
              return (
                <button
                  key={s.key}
                  onClick={() => onPickSession(s)}
                  className={`flex w-20 shrink-0 flex-col items-center gap-1 rounded-xl border p-1.5 ${
                    active ? "border-accent/70 bg-ink-800" : "border-ink-700 bg-ink-900"
                  }`}
                >
                  <div className="relative h-20 w-14 overflow-hidden rounded-md bg-ink-800">
                    {s.card.imageSmall && (
                      <Image src={s.card.imageSmall} alt={s.card.name} fill sizes="56px" className="object-cover" unoptimized />
                    )}
                  </div>
                  <span className="line-clamp-1 text-[10px] text-ink-300">{s.card.name}</span>
                  <span className="text-[10px] font-medium text-ink-100">
                    {p?.marketUsd != null ? `$${p.marketUsd.toFixed(2)}` : "—"}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      )}

      <div className="flex justify-center">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1.5 rounded-full bg-accent px-5 py-2.5 text-sm font-semibold text-ink-950 shadow-lg shadow-accent/20 active:scale-95"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M3 8V5a2 2 0 0 1 2-2h3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M21 16v3a2 2 0 0 1-2 2h-3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <path d="M7 12h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          다음 카드 스캔
        </button>
      </div>

      <div className="flex gap-3">
        {card.imageSmall && (
          <div className="relative h-40 w-28 shrink-0 overflow-hidden rounded-xl bg-ink-800">
            <Image src={card.imageSmall} alt={card.name} fill sizes="112px" className="object-cover" unoptimized />
          </div>
        )}
        <div className="flex flex-col justify-between py-1">
          <div>
            <h2 className="text-lg font-semibold leading-tight text-ink-100">{card.name}</h2>
            <p className="mt-0.5 text-xs text-ink-300">
              {card.setName} · {card.number}
              {card.setPrintedTotal ? `/${card.setPrintedTotal}` : ""}
            </p>
            {card.artist && <p className="mt-0.5 text-[11px] text-ink-500">illus. {card.artist}</p>}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {card.locale !== "en" && (
              <Chip>{card.locale === "jp" ? "JP" : "KR"}</Chip>
            )}
            {card.rarity && <Chip>{card.rarity}</Chip>}
            {card.types.map((t) => (
              <Chip key={t}>{t}</Chip>
            ))}
            {card.subtypes.map((t) => (
              <Chip key={t}>{t}</Chip>
            ))}
          </div>
        </div>
      </div>

      <PriceDisplay card={card} />

      {(card.hp || card.weaknesses.length > 0 || card.resistances.length > 0) && (
        <section className="grid grid-cols-3 gap-2">
          {card.hp && <MiniStat label="HP" value={card.hp} />}
          {card.weaknesses[0] && <MiniStat label="약점" value={`${card.weaknesses[0].type} ${card.weaknesses[0].value}`} />}
          {card.resistances[0] && <MiniStat label="저항" value={`${card.resistances[0].type} ${card.resistances[0].value}`} />}
        </section>
      )}

      {card.attacks.length > 0 && (
        <section className="rounded-2xl border border-ink-700 bg-ink-900 p-4">
          <p className="text-xs uppercase tracking-wider text-ink-400">기술</p>
          <ul className="mt-2 space-y-3">
            {card.attacks.map((a) => (
              <li key={a.name}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm font-medium text-ink-100">{a.name}</span>
                  {a.damage && <span className="text-sm text-accent">{a.damage}</span>}
                </div>
                {a.cost.length > 0 && <p className="text-[11px] text-ink-400">에너지: {a.cost.join(" · ")}</p>}
                {a.text && <p className="mt-1 text-xs leading-relaxed text-ink-300">{a.text}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-2xl border border-ink-700 bg-ink-900 p-4">
        <p className="text-xs uppercase tracking-wider text-ink-400">분석</p>
        {analysis ? (
          <dl className="mt-2 space-y-2 text-sm text-ink-200">
            <Row label="희귀도" value={analysis.rarityNote} />
            <Row label="세트" value={analysis.setContext} />
            <Row label="수집" value={analysis.collectibility} />
            <Row label="투자" value={analysis.investment} />
          </dl>
        ) : (
          <p className="mt-2 text-sm text-ink-300">이 카드에 대한 분석 데이터가 부족합니다.</p>
        )}
      </section>

      {card.flavorText && (
        <p className="rounded-2xl border border-ink-700 bg-ink-900 p-4 text-xs leading-relaxed text-ink-300">
          &ldquo;{card.flavorText}&rdquo;
        </p>
      )}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full border border-ink-600 px-2 py-0.5 text-[10px] text-ink-200">{children}</span>;
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-ink-700 bg-ink-900 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-ink-400">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-ink-100">{value}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-ink-400">{label}</dt>
      <dd className="mt-0.5 leading-relaxed">{value}</dd>
    </div>
  );
}
