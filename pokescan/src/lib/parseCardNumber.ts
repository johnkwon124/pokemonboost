/**
 * Card numbers on Pokemon cards typically look like:
 *   "025/198", "SV-P 042", "SWSH284", "TG12/TG30", "1/102"
 * The "X/Y" form is the most common on modern English cards and the most reliable
 * fragment to OCR. We pull every plausible candidate so the lookup layer can try
 * the best matches first.
 */

export interface ParsedNumber {
  raw: string;
  number: string;
  printedTotal: number | null;
}

const PATTERNS: RegExp[] = [
  // "025/198", "1/102", "TG12/TG30"
  /\b([A-Z]{0,4}\d{1,4})\s*\/\s*([A-Z]{0,4}\d{1,4})\b/g,
  // "SWSH284", "SV-P 042" (promo style, no total)
  /\b(SWSH|SM|XY|BW|HGSS|SV[- ]?P|SVP)\s*[- ]?\s*(\d{1,4})\b/gi
];

export function parseCardNumbers(text: string): ParsedNumber[] {
  if (!text) return [];
  const cleaned = text.replace(/[Oo](?=\d)/g, "0").replace(/\s+/g, " ");
  const seen = new Set<string>();
  const out: ParsedNumber[] = [];

  for (const re of PATTERNS) {
    re.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = re.exec(cleaned)) !== null) {
      if (match[2] !== undefined && /^\d/.test(match[2])) {
        const raw = `${match[1]}/${match[2]}`;
        if (seen.has(raw)) continue;
        seen.add(raw);
        const total = Number(match[2].replace(/\D/g, ""));
        const num = Number(match[1].replace(/\D/g, ""));
        // Drop only obvious noise like a height "5' 7\"" → "5/7". Keep secret/
        // rainbow rares whose number legitimately exceeds the set total
        // (e.g. 198/197), so only filter num > total when the total is tiny.
        if (Number.isFinite(total) && total < 10 && Number.isFinite(num) && num > total) continue;
        out.push({
          raw,
          number: match[1].replace(/^0+/, "") || match[1],
          printedTotal: Number.isFinite(total) ? total : null
        });
      } else {
        const raw = `${match[1]}${match[2]}`.toUpperCase();
        if (seen.has(raw)) continue;
        seen.add(raw);
        out.push({ raw, number: raw, printedTotal: null });
      }
    }
  }

  // Prefer the most identifying candidates: those with a realistic set total
  // (>= 10) first, larger totals first (modern sets), then the rest.
  return out.sort((a, b) => score(b) - score(a));
}

function score(p: ParsedNumber): number {
  if (p.printedTotal === null) return 0;
  if (p.printedTotal < 10) return 1;
  return 100 + Math.min(p.printedTotal, 999);
}

/**
 * Best-effort card name guess from full-card OCR text (used only by the manual
 * "사진으로 시도" fallback, which may capture the whole card).
 */
export function guessCardName(text: string): string | null {
  if (!text) return null;
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  for (const line of lines) {
    const letters = line.replace(/[^A-Za-z]/g, "");
    if (letters.length >= 3 && letters.length / line.length > 0.55 && line.length < 30) {
      return line;
    }
  }
  return null;
}
