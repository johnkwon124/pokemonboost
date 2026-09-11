import { runVisionOcr } from "./visionClient";
import { parseCardNumbers, type ParsedNumber } from "./parseCardNumber";
import { findCardByNumber, findCardsByName, asLocalized } from "./tcg";
import { extractNameTokens, resolveEnglishSpecies } from "./pokedex";
import { extractCardHints, narrowByHints } from "./cardHints";
import { detectCardLang, type CardLang } from "./lang";
import { buildStaticAnalysis } from "./staticAnalysis";
import type { Analysis, Card } from "@/types/card";

export interface ScanOutcome {
  card: Card;
  analysis: Analysis | null;
  ocrText: string;
}

/** Multiple English printings matched a JP/KR card — the user picks one. */
export interface ScanChoices {
  kind: "choices";
  candidates: Card[];
  matchedName: string;
  lang: "ja" | "ko";
}

export interface FrameAnalysis {
  text: string;
  lang: CardLang;
  parsed: ParsedNumber | null;
}

export class ScanNotFoundError extends Error {
  constructor(message: string, public ocrText = "") {
    super(message);
    this.name = "ScanNotFoundError";
  }
}

/** OCR a frame once and derive everything downstream steps need. */
export async function analyzeFrame(imageBase64: string): Promise<FrameAnalysis> {
  const text = await runVisionOcr(imageBase64);
  const candidates = parseCardNumbers(text).filter((n) => n.printedTotal !== null);
  return { text, lang: detectCardLang(text), parsed: candidates[0] ?? null };
}

/** English path: strict (number, set total) lookup. */
export async function lookupEnglish(parsed: ParsedNumber): Promise<ScanOutcome | null> {
  const card = await findCardByNumber(parsed.number, parsed.printedTotal);
  if (!card) return null;
  return { card, analysis: buildStaticAnalysis(card), ocrText: parsed.raw };
}

/**
 * JP/KR path: no free database carries Japanese/Korean-exclusive set numbering
 * (TCGdex only localizes international sets), so identifying by collector
 * number is impossible. Instead we read the Pokémon NAME — the largest text on
 * the card — translate it to English via the species dictionary, and match the
 * English printings. Prices shown from these are English-market estimates.
 */
export async function resolveJpKr(text: string, lang: "ja" | "ko"): Promise<ScanOutcome | ScanChoices> {
  const tokens = extractNameTokens(text, lang);
  if (tokens.length === 0) {
    throw new ScanNotFoundError("카드 이름을 읽지 못했어요. 카드 상단 이름이 잘 보이게 비춰주세요", text);
  }

  let hit;
  try {
    hit = await resolveEnglishSpecies(tokens, lang);
  } catch {
    throw new ScanNotFoundError("포켓몬 이름 사전을 불러오지 못했어요. 네트워크 확인 후 다시 시도해주세요", text);
  }
  if (!hit) {
    throw new ScanNotFoundError(
      "포켓몬 이름을 찾지 못했어요. 포켓몬 카드가 맞는지 확인해주세요 (트레이너/에너지 카드는 영문판만 지원)",
      text
    );
  }

  const locale = lang === "ja" ? "jp" : "kr";
  const all = (await findCardsByName(hit.en)).map((c) => asLocalized(c, locale));
  if (all.length === 0) {
    throw new ScanNotFoundError(`"${hit.en}" 카드를 DB에서 찾지 못했어요`, text);
  }

  // Narrow by HP + mechanic suffix read from the same OCR pass — a card keeps
  // both across languages, so this often collapses the list to the exact card.
  const hints = extractCardHints(text);
  const candidates = narrowByHints(all, hints).slice(0, 8);

  if (candidates.length === 1) {
    return { card: candidates[0], analysis: buildStaticAnalysis(candidates[0]), ocrText: hit.matchedToken };
  }
  return { kind: "choices", candidates, matchedName: `${hit.matchedToken} (${hit.en})`, lang };
}

/** Build a final outcome from a user-picked candidate. */
export function outcomeFromPick(card: Card, matchedName: string): ScanOutcome {
  return { card, analysis: buildStaticAnalysis(card), ocrText: matchedName };
}
