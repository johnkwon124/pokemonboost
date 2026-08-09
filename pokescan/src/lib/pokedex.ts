/**
 * Pokémon species name dictionary (ja/ko → en), lazily loaded from PokeAPI's
 * public CSV on GitHub raw (CORS-enabled, ~400KB, fetched only when a JP/KR
 * card is scanned and cached in memory for the session).
 *
 * This exists because no free card DB carries Japanese/Korean-exclusive set
 * numbering — so for JP/KR cards we identify the Pokémon by NAME and match it
 * to its English printings instead.
 */

const CSV_URL =
  "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/pokemon_species_names.csv";

// PokeAPI local_language_id: 1 = ja-Hrkt (katakana), 11 = ja, 3 = ko, 9 = en
const LANG_JA = new Set(["1", "11"]);
const LANG_KO = "3";
const LANG_EN = "9";

interface SpeciesMaps {
  ja: Map<string, number>;
  ko: Map<string, number>;
  en: Map<number, string>;
}

let mapsPromise: Promise<SpeciesMaps> | null = null;

async function loadMaps(): Promise<SpeciesMaps> {
  const res = await fetch(CSV_URL);
  if (!res.ok) throw new Error(`species CSV ${res.status}`);
  const text = await res.text();
  const maps: SpeciesMaps = { ja: new Map(), ko: new Map(), en: new Map() };
  for (const line of text.split("\n")) {
    const firstComma = line.indexOf(",");
    const secondComma = line.indexOf(",", firstComma + 1);
    const thirdComma = line.indexOf(",", secondComma + 1);
    if (firstComma < 0 || secondComma < 0) continue;
    const id = Number(line.slice(0, firstComma));
    if (!Number.isFinite(id)) continue;
    const langId = line.slice(firstComma + 1, secondComma);
    const name = (thirdComma > 0 ? line.slice(secondComma + 1, thirdComma) : line.slice(secondComma + 1)).trim();
    if (!name) continue;
    if (LANG_JA.has(langId)) maps.ja.set(name, id);
    else if (langId === LANG_KO) maps.ko.set(name, id);
    else if (langId === LANG_EN) maps.en.set(id, name);
  }
  if (maps.en.size === 0) throw new Error("species CSV parsed empty");
  return maps;
}

function getMaps(): Promise<SpeciesMaps> {
  if (!mapsPromise) {
    mapsPromise = loadMaps().catch((e) => {
      // don't cache failures — allow a retry on the next scan
      mapsPromise = null;
      throw e;
    });
  }
  return mapsPromise;
}

/** Extract candidate name tokens (pure-script runs) from OCR text, in reading order. */
export function extractNameTokens(text: string, lang: "ja" | "ko"): string[] {
  const re = lang === "ja" ? /[ァ-ヶー]{2,}/g : /[가-힣]{2,}/g;
  const seen = new Set<string>();
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null && out.length < 20) {
    if (!seen.has(m[0])) {
      seen.add(m[0]);
      out.push(m[0]);
    }
  }
  return out;
}

export interface SpeciesHit {
  en: string;
  matchedToken: string;
}

/**
 * Find the first token that is a known species name. Card names put the
 * Pokémon name near the top, and OCR text is roughly top-to-bottom, so the
 * first dictionary hit is almost always the card's Pokémon.
 */
export async function resolveEnglishSpecies(tokens: string[], lang: "ja" | "ko"): Promise<SpeciesHit | null> {
  if (tokens.length === 0) return null;
  const maps = await getMaps();
  const dict = lang === "ja" ? maps.ja : maps.ko;
  for (const token of tokens) {
    const direct = dict.get(token);
    if (direct !== undefined) {
      const en = maps.en.get(direct);
      if (en) return { en, matchedToken: token };
    }
  }
  // Second pass: a token may carry a glued suffix or prefix (regional form,
  // rarity letters clipped by OCR). Try substring containment both ways on
  // longer tokens.
  for (const token of tokens) {
    if (token.length < 3) continue;
    for (const [name, id] of dict) {
      if (name.length >= 3 && (token.includes(name) || name.includes(token))) {
        const en = maps.en.get(id);
        if (en) return { en, matchedToken: token };
      }
    }
  }
  return null;
}
