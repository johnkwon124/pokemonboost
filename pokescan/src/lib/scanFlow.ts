import { runVisionOcr } from "./visionClient";
import { parseCardNumbers, type ParsedNumber } from "./parseCardNumber";
import { findCardByNumber } from "./tcg";
import { findJpKrCardByNumber } from "./tcgdex";
import { detectCardLang, type CardLang } from "./lang";
import { buildStaticAnalysis } from "./staticAnalysis";
import type { Analysis, Card } from "@/types/card";

export interface ScanOutcome {
  card: Card;
  analysis: Analysis | null;
  ocrText: string;
}

export interface OcrCandidate {
  parsed: ParsedNumber;
  lang: CardLang;
}

export class ScanNotFoundError extends Error {
  constructor(public ocrText: string) {
    super("카드를 찾지 못했습니다");
    this.name = "ScanNotFoundError";
  }
}

/**
 * OCR a captured frame and return the best collector-number candidate plus the
 * detected card language. Returns null if nothing usable was read. Kept separate
 * from the DB lookup so the scanner can require two consecutive reads to agree
 * before committing — this kills transient misreads that otherwise load the
 * wrong card.
 */
export async function ocrCardNumber(imageBase64: string): Promise<OcrCandidate | null> {
  const text = await runVisionOcr(imageBase64);
  if (!text.trim()) return null;
  const candidates = parseCardNumbers(text).filter((n) => n.printedTotal !== null);
  if (!candidates[0]) return null;
  return { parsed: candidates[0], lang: detectCardLang(text) };
}

async function tryLookup(lang: CardLang, parsed: ParsedNumber): Promise<Card | null> {
  if (lang === "ja" || lang === "ko") {
    return findJpKrCardByNumber(lang, parsed.number, parsed.printedTotal);
  }
  return findCardByNumber(parsed.number, parsed.printedTotal);
}

/**
 * Resolve a parsed number to a card + analysis, starting with the language
 * detected from the OCR text and falling back to the other databases if it
 * doesn't match. Each individual lookup is strict (printed total must match
 * exactly), so the fallback chain can't accidentally surface a wrong card —
 * it only succeeds if a card with the *exact same* (number, set total) exists
 * in another language DB.
 */
export async function lookupCard(
  parsed: ParsedNumber,
  lang: CardLang = "en"
): Promise<ScanOutcome | null> {
  const order: CardLang[] = lang === "en" ? ["en", "ja", "ko"] : [lang, "en", lang === "ja" ? "ko" : "ja"];
  for (const tryLang of order) {
    const card = await tryLookup(tryLang, parsed);
    if (card) return { card, analysis: buildStaticAnalysis(card), ocrText: parsed.raw };
  }
  return null;
}

/** One-shot convenience used by the manual capture fallback. */
export async function scanImage(imageBase64: string): Promise<ScanOutcome> {
  const candidate = await ocrCardNumber(imageBase64);
  if (!candidate) throw new ScanNotFoundError("");
  const outcome = await lookupCard(candidate.parsed, candidate.lang);
  if (!outcome) throw new ScanNotFoundError(candidate.parsed.raw);
  return outcome;
}
