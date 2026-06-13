import { runVisionOcr } from "./visionClient";
import { parseCardNumbers, type ParsedNumber } from "./parseCardNumber";
import { findCardByNumber } from "./tcg";
import { buildStaticAnalysis } from "./staticAnalysis";
import type { Analysis, Card } from "@/types/card";

export interface ScanOutcome {
  card: Card;
  analysis: Analysis | null;
  ocrText: string;
}

export class ScanNotFoundError extends Error {
  constructor(public ocrText: string) {
    super("카드를 찾지 못했습니다");
    this.name = "ScanNotFoundError";
  }
}

/**
 * OCR a captured frame and return the best collector-number candidate (one that
 * includes a set total, the reliable identifier). Returns null if nothing usable
 * was read. Kept separate from the DB lookup so the scanner can require two
 * consecutive reads to agree before committing — this kills transient misreads
 * that otherwise load the wrong card.
 */
export async function ocrCardNumber(imageBase64: string): Promise<ParsedNumber | null> {
  const text = await runVisionOcr(imageBase64);
  if (!text.trim()) return null;
  const candidates = parseCardNumbers(text).filter((n) => n.printedTotal !== null);
  return candidates[0] ?? null;
}

/** Resolve a parsed number to a card + analysis, or null if no set matches. */
export async function lookupCard(parsed: ParsedNumber): Promise<ScanOutcome | null> {
  const card = await findCardByNumber(parsed.number, parsed.printedTotal);
  if (!card) return null;
  return { card, analysis: buildStaticAnalysis(card), ocrText: parsed.raw };
}

/** One-shot convenience used by the manual capture fallback. */
export async function scanImage(imageBase64: string): Promise<ScanOutcome> {
  const parsed = await ocrCardNumber(imageBase64);
  if (!parsed) throw new ScanNotFoundError("");
  const outcome = await lookupCard(parsed);
  if (!outcome) throw new ScanNotFoundError(parsed.raw);
  return outcome;
}
