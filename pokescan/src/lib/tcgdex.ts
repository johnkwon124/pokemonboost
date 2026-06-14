import type { Card } from "@/types/card";

/**
 * TCGdex client — free, public, CORS-enabled REST API with native Japanese and
 * Korean card data. We use it as the data source whenever OCR detects a JP/KR
 * card. Pricing isn't included (TCGdex doesn't track JP/KR market prices), so
 * the result is the card info itself + "시세 데이터 없음".
 *
 * Lookup strategy: list cards by `localId` (collector number), then disambiguate
 * by the set's printed total using a cached set list (one fetch per language,
 * reused for the session).
 */

const BASE = "https://api.tcgdex.net/v2";

type Lang = "ja" | "ko";

interface TcgdexBrief {
  id: string;
  localId?: string;
  name: string;
  image?: string;
}

interface TcgdexSet {
  id: string;
  name: string;
  serie?: { id: string; name: string };
  releaseDate?: string;
  cardCount?: { total?: number; official?: number };
}

interface TcgdexCardFull {
  id: string;
  localId?: string;
  name: string;
  image?: string;
  category?: string;
  rarity?: string;
  hp?: number;
  types?: string[];
  illustrator?: string;
  set?: TcgdexSet;
}

const setCache = new Map<Lang, Promise<Map<string, TcgdexSet>>>();

async function loadSets(lang: Lang): Promise<Map<string, TcgdexSet>> {
  const cached = setCache.get(lang);
  if (cached) return cached;
  const promise = (async () => {
    const res = await fetch(`${BASE}/${lang}/sets`);
    const out = new Map<string, TcgdexSet>();
    if (!res.ok) return out;
    const sets = (await res.json()) as TcgdexSet[];
    for (const s of sets) out.set(s.id, s);
    return out;
  })();
  setCache.set(lang, promise);
  return promise;
}

async function fetchBriefs(lang: Lang, localId: string): Promise<TcgdexBrief[]> {
  // TCGdex filters default to a laxist (partial / case-insensitive) match, so
  // `?localId=28` would also match "128", "028", "281", etc. and we'd get
  // hundreds of irrelevant cards. Doubling the `=` (`localId==28`) forces an
  // exact match — without this the lookup picks the wrong card almost every
  // time on common low numbers.
  const url = `${BASE}/${lang}/cards?localId==${encodeURIComponent(localId)}`;
  const res = await fetch(url);
  if (!res.ok) return [];
  const json = (await res.json()) as TcgdexBrief[] | unknown;
  return Array.isArray(json) ? json : [];
}

/**
 * Each brief card id is of the form `{setId}-{localId}`. Set ids can contain
 * hyphens (e.g. `sv-p` promo set), so split by matching against the known set
 * map rather than by the rightmost dash.
 */
function resolveSet(briefId: string, sets: Map<string, TcgdexSet>): TcgdexSet | null {
  // setIds can contain hyphens (e.g. `sv-p`) and one id may be a prefix of
  // another (e.g. `sv` vs `sv-p`), so pick the longest matching set id.
  let best: TcgdexSet | null = null;
  for (const set of sets.values()) {
    if (briefId.startsWith(set.id + "-") && (!best || set.id.length > best.id.length)) {
      best = set;
    }
  }
  return best;
}

function getSetTotal(set: TcgdexSet): number | null {
  return set.cardCount?.official ?? set.cardCount?.total ?? null;
}

function normalize(raw: TcgdexCardFull, lang: Lang): Card {
  const localeFlag: Card["locale"] = lang === "ja" ? "jp" : "kr";
  const imgBase = raw.image;
  return {
    id: `tcgdex-${lang}-${raw.id}`,
    name: raw.name,
    number: raw.localId ?? "",
    setId: raw.set?.id ?? "",
    setName: raw.set?.name ?? "",
    setSeries: raw.set?.serie?.name ?? null,
    setPrintedTotal: raw.set ? getSetTotal(raw.set) : null,
    releaseDate: raw.set?.releaseDate ?? null,
    rarity: raw.rarity ?? null,
    supertype: raw.category ?? null,
    subtypes: [],
    types: raw.types ?? [],
    hp: raw.hp != null ? String(raw.hp) : null,
    imageSmall: imgBase ? `${imgBase}/low.webp` : null,
    imageLarge: imgBase ? `${imgBase}/high.webp` : null,
    attacks: [],
    weaknesses: [],
    resistances: [],
    flavorText: null,
    artist: raw.illustrator ?? null,
    prices: [],
    locale: localeFlag,
    estimated: false
  };
}

export async function findJpKrCardByNumber(
  lang: Lang,
  number: string,
  printedTotal: number | null
): Promise<Card | null> {
  // Some sets pad localId, some don't — try both forms in parallel.
  const padded = number.padStart(3, "0");
  const [briefsA, briefsB] = await Promise.all([
    fetchBriefs(lang, number),
    number !== padded ? fetchBriefs(lang, padded) : Promise.resolve([] as TcgdexBrief[])
  ]);

  const seen = new Set<string>();
  const briefs = [...briefsA, ...briefsB].filter((b) => (seen.has(b.id) ? false : (seen.add(b.id), true)));
  if (briefs.length === 0) return null;

  const sets = await loadSets(lang);

  let chosenId: string | null = null;
  if (printedTotal !== null) {
    for (const brief of briefs) {
      const set = resolveSet(brief.id, sets);
      if (set && getSetTotal(set) === printedTotal) {
        chosenId = brief.id;
        break;
      }
    }
  } else if (briefs[0]) {
    chosenId = briefs[0].id;
  }
  if (!chosenId) return null;

  const res = await fetch(`${BASE}/${lang}/cards/${encodeURIComponent(chosenId)}`);
  if (!res.ok) return null;
  const full = (await res.json()) as TcgdexCardFull;
  return normalize(full, lang);
}
