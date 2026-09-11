import type { Card } from "@/types/card";

/**
 * Extra identity clues pulled from full-card OCR text, used to narrow the
 * English-printing candidates for a JP/KR card. The same card keeps the same
 * HP and mechanic suffix (ex/V/VMAX/VSTAR/GX) across languages, so these are
 * strong filters even though the collector numbering differs.
 */
export interface CardHints {
  hp: string | null;
  mechanic: "VMAX" | "VSTAR" | "GX" | "ex" | "V" | null;
}

export function extractCardHints(text: string): CardHints {
  const hpMatch = text.match(/HP\s*([1-9]\d{1,2})\b/i) ?? text.match(/\b([1-9]\d{1,2})\s*HP/i);

  let mechanic: CardHints["mechanic"] = null;
  if (/VMAX/i.test(text)) mechanic = "VMAX";
  else if (/VSTAR/i.test(text)) mechanic = "VSTAR";
  else if (/\bGX\b/.test(text)) mechanic = "GX";
  // "ex" is glued to the name on JP/KR cards (リザードンex / 리자몽ex)
  else if (/[ァ-ヶー가-힣]\s?ex\b/i.test(text) || /\bex\b/.test(text)) mechanic = "ex";
  else if (/[ァ-ヶー가-힣]\s?V(?![A-Za-z])/.test(text)) mechanic = "V";

  return { hp: hpMatch ? hpMatch[1] : null, mechanic };
}

function nameMatchesMechanic(name: string, mechanic: NonNullable<CardHints["mechanic"]>): boolean {
  switch (mechanic) {
    case "VMAX":
      return /vmax/i.test(name);
    case "VSTAR":
      return /vstar/i.test(name);
    case "GX":
      return /\bgx\b/i.test(name);
    case "ex":
      return /\bex\b/i.test(name);
    case "V":
      return /\sV$/.test(name);
  }
}

const ANY_MECHANIC = /\b(ex|gx|vmax|vstar)\b|\sV$/i;

/**
 * Soft-narrow candidates by mechanic suffix and HP: apply each filter only
 * when it leaves at least one candidate, so an OCR miss never empties the list.
 */
export function narrowByHints(candidates: Card[], hints: CardHints): Card[] {
  let out = candidates;

  if (hints.mechanic) {
    const m = out.filter((c) => nameMatchesMechanic(c.name, hints.mechanic!));
    if (m.length > 0) out = m;
  } else {
    // no mechanic on the scanned card → prefer plain printings
    const plain = out.filter((c) => !ANY_MECHANIC.test(c.name));
    if (plain.length > 0) out = plain;
  }

  if (hints.hp) {
    const h = out.filter((c) => c.hp === hints.hp);
    if (h.length > 0) out = h;
  }

  return out;
}
