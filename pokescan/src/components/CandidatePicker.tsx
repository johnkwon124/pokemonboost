"use client";

import Image from "next/image";
import type { Card } from "@/types/card";
import { pickGeneralPrice } from "@/lib/tcg";

interface Props {
  matchedName: string;
  lang: "ja" | "ko";
  candidates: Card[];
  onPick: (card: Card) => void;
  onCancel: () => void;
}

/**
 * JP/KR cards are identified by Pokémon name, which can map to several English
 * printings. Card art makes them trivially distinguishable by eye, so we let
 * the user tap the one they're holding.
 */
export default function CandidatePicker({ matchedName, lang, candidates, onPick, onCancel }: Props) {
  return (
    <div className="flex flex-col gap-4 px-4 pb-8">
      <div className="flex items-center justify-between">
        <button onClick={onCancel} className="text-sm text-ink-300 active:opacity-60">
          ← 다시 스캔
        </button>
        <span className="rounded-full border border-ink-700 px-2 py-0.5 text-[10px] uppercase tracking-wider text-ink-300">
          {lang === "ja" ? "일본어 카드" : "한국어 카드"}
        </span>
      </div>

      <div>
        <h2 className="text-base font-semibold text-ink-100">{matchedName}</h2>
        <p className="mt-1 text-xs leading-relaxed text-ink-400">
          들고 있는 카드와 같은 일러스트를 선택하세요. 시세는 동일 카드 영문판 기준 추정치입니다.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {candidates.map((card) => {
          const price = pickGeneralPrice(card);
          return (
            <button
              key={card.id}
              onClick={() => onPick(card)}
              className="flex flex-col overflow-hidden rounded-xl border border-ink-700 bg-ink-900 text-left active:scale-[0.98]"
            >
              <div className="relative aspect-[5/7] w-full bg-ink-800">
                {card.imageSmall && (
                  <Image src={card.imageSmall} alt={card.name} fill sizes="45vw" className="object-cover" unoptimized />
                )}
              </div>
              <div className="flex flex-col gap-0.5 p-2">
                <span className="line-clamp-1 text-xs font-medium text-ink-100">{card.name}</span>
                <span className="line-clamp-1 text-[10px] text-ink-400">
                  {card.setName} · {card.number}
                  {card.setPrintedTotal ? `/${card.setPrintedTotal}` : ""}
                </span>
                <span className="text-xs font-semibold text-accent">
                  {price?.marketUsd != null ? `$${price.marketUsd.toFixed(2)}` : "시세 없음"}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
