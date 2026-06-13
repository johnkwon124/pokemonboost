import type { Analysis, Card } from "@/types/card";

/**
 * Rule-based analysis derived purely from TCG metadata — no external AI calls.
 */
export function buildStaticAnalysis(card: Card): Analysis | null {
  const rarityNote = rarityCommentary(card.rarity);
  const setContext = setCommentary(card);
  const collectibility = collectCommentary(card);
  const investment = investmentCommentary(card);
  if (!rarityNote && !setContext && !collectibility && !investment) return null;
  return {
    rarityNote: rarityNote ?? "희귀도 정보가 부족합니다.",
    setContext: setContext ?? "세트 정보가 부족합니다.",
    collectibility: collectibility ?? "수집 관점 데이터가 부족합니다.",
    investment: investment ?? "투자 관점 데이터가 부족합니다.",
    source: "tcg-api"
  };
}

function rarityCommentary(rarity: string | null): string | null {
  if (!rarity) return null;
  const r = rarity.toLowerCase();
  if (r.includes("secret")) return "시크릿 레어 — 세트 내 가장 희소한 등급 중 하나로 박스당 출현 빈도가 매우 낮습니다.";
  if (r.includes("hyper") || r.includes("rainbow")) return "레인보우/하이퍼 레어 — 박스당 1장 미만으로 등장하는 슈퍼 챔피언급 등급입니다.";
  if (r.includes("illustration rare") || r.includes("special illustration")) return "일러스트 레어 — 풀아트 아트워크가 핵심 가치 포인트이며 수집 수요가 높습니다.";
  if (r.includes("ultra")) return "울트라 레어 — 박스당 1~2장 출현, 대회 수요와 컬렉터 수요가 겹치는 등급입니다.";
  if (r.includes("holo") && r.includes("rare")) return "홀로 레어 — 박스 내 표준 홀로 슬롯에 등장, 가격대는 중간 정도입니다.";
  if (r === "rare") return "레어 — 박스당 다수 등장하며 시세는 낮은 편이지만 메타 카드라면 수요가 붙습니다.";
  if (r === "uncommon" || r === "common") return "일반 카드 — 박스당 다수 등장, 시세 자체는 매우 낮지만 메타 사용처에 따라 변동.";
  return `희귀도: ${rarity}.`;
}

function setCommentary(card: Card): string | null {
  const parts: string[] = [];
  if (card.setName) parts.push(`${card.setName} 세트`);
  if (card.setSeries) parts.push(`${card.setSeries} 시리즈`);
  if (card.releaseDate) parts.push(`${card.releaseDate} 발매`);
  if (card.setPrintedTotal) parts.push(`총 ${card.setPrintedTotal}종`);
  if (!parts.length) return null;
  return parts.join(" · ") + "에 수록되었습니다.";
}

function collectCommentary(card: Card): string | null {
  const r = (card.rarity ?? "").toLowerCase();
  if (r.includes("illustration") || r.includes("rainbow") || r.includes("secret")) {
    return "아트워크 중심의 컬렉션 카드로, 그레이딩 수요(PSA 10)도 형성되어 있으나 본 앱은 raw NM 기준 시세를 보여줍니다.";
  }
  if (card.subtypes.includes("V") || card.subtypes.includes("VMAX") || card.subtypes.includes("ex")) {
    return "대회 메타에서 활용 가능한 매커닉 카드로, 시세는 발매 직후 가장 높고 로테이션 시점에 떨어지는 경향이 있습니다.";
  }
  if (card.flavorText) return `플레이버 텍스트: ${card.flavorText}`;
  return "스탠다드 카드로 컬렉션 완성용 수요가 주력입니다.";
}

function investmentCommentary(card: Card): string | null {
  if (card.locale === "jp") {
    return "일본어 카드는 별도 시세 데이터가 없어 가격을 표시하지 않습니다. 동일 영문판이 있다면 그 시세를 참고하세요.";
  }
  if (card.locale === "kr") {
    return "한국어 카드는 별도 시세 데이터가 없어 가격을 표시하지 않습니다. 영문판/일본어판이 존재한다면 그 시세를 참고하세요.";
  }
  const r = (card.rarity ?? "").toLowerCase();
  if (r.includes("rainbow") || r.includes("secret") || r.includes("illustration")) {
    return "장기적으로 인쇄가 종료된 후 상승 여력이 있는 등급. 단기 변동성보다는 1~2년 단위로 보는 것이 일반적입니다.";
  }
  if (r === "common" || r === "uncommon" || r === "rare") {
    return "낮은 단가로 단기 차익 기대는 낮습니다. 다만 메타 채택 시 일시적으로 급등하는 사례가 있습니다.";
  }
  return "현재 시세는 거래량과 메타 변화에 민감하니 표시된 raw NM 시세를 가이드 라인으로 사용하세요.";
}
