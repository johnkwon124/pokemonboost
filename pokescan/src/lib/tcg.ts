import type { Card, MarketPrice, PriceVariant } from "@/types/card";

/**
 * Pokemon TCG API client. The API is public, CORS-enabled and needs no auth,
 * so this runs directly in the browser. An optional public key raises the rate
 * limit but is not required.
 */

const TCG_API = "https://api.pokemontcg.io/v2";
const KEY = process.env.NEXT_PUBLIC_POKEMONTCG_API_KEY;

interface TcgPriceBlock {
  low: number | null;
  mid: number | null;
  high: number | null;
  market: number | null;
}

interface TcgCard {
  id: string;
  name: string;
  number: string;
  supertype?: string;
  subtypes?: string[];
  types?: string[];
  hp?: string;
  images: { small: string; large: string };
  attacks?: { name: string; cost: string[]; damage: string; text: string }[];
  weaknesses?: { type: string; value: string }[];
  resistances?: { type: string; value: string }[];
  flavorText?: string;
  artist?: string;
  rarity?: string;
  set: {
    id: string;
    name: string;
    series?: string;
    printedTotal?: number;
    releaseDate?: string;
  };
  tcgplayer?: {
    updatedAt?: string;
    prices?: Partial<Record<PriceVariant, TcgPriceBlock>>;
  };
}

function headers(): HeadersInit {
  return KEY ? { "X-Api-Key": KEY } : {};
}

function toPrices(raw: TcgCard): MarketPrice[] {
  const prices = raw.tcgplayer?.prices;
  if (!prices) return [];
  const updatedAt = raw.tcgplayer?.updatedAt ?? null;
  const out: MarketPrice[] = [];
  for (const [variant, block] of Object.entries(prices) as [PriceVariant, TcgPriceBlock][]) {
    if (!block) continue;
    out.push({
      variant,
      marketUsd: block.market ?? null,
      lowUsd: block.low ?? null,
      midUsd: block.mid ?? null,
      highUsd: block.high ?? null,
      updatedAt,
      source: "tcgplayer"
    });
  }
  return out;
}

function normalize(raw: TcgCard, locale: "en" | "jp" = "en", estimated = false): Card {
  return {
    id: raw.id,
    name: raw.name,
    number: raw.number,
    setId: raw.set.id,
    setName: raw.set.name,
    setSeries: raw.set.series ?? null,
    setPrintedTotal: raw.set.printedTotal ?? null,
    releaseDate: raw.set.releaseDate ?? null,
    rarity: raw.rarity ?? null,
    supertype: raw.supertype ?? null,
    subtypes: raw.subtypes ?? [],
    types: raw.types ?? [],
    hp: raw.hp ?? null,
    imageSmall: raw.images?.small ?? null,
    imageLarge: raw.images?.large ?? null,
    attacks: raw.attacks ?? [],
    weaknesses: raw.weaknesses ?? [],
    resistances: raw.resistances ?? [],
    flavorText: raw.flavorText ?? null,
    artist: raw.artist ?? null,
    prices: toPrices(raw),
    locale,
    estimated
  };
}

async function tcgQuery(q: string, pageSize = 12): Promise<TcgCard[]> {
  const url = `${TCG_API}/cards?q=${encodeURIComponent(q)}&pageSize=${pageSize}&orderBy=-set.releaseDate`;
  const res = await fetch(url, { headers: headers() });
  if (!res.ok) return [];
  const json = (await res.json()) as { data?: TcgCard[] };
  return json.data ?? [];
}

function sameNumber(a: string, b: string): boolean {
  const norm = (s: string) => s.replace(/^0+/, "").toUpperCase();
  return norm(a) === norm(b);
}

/**
 * The set total (the "/198" part) is what disambiguates same-numbered cards
 * across sets (028/150 vs 028/255). Querying number + set.printedTotal together
 * returns just the 1–3 matching cards instead of hundreds, so it's both fast and
 * unambiguous. If no set matches, return nothing rather than guess the wrong card.
 */
export async function findCardByNumber(number: string, printedTotal: number | null): Promise<Card | null> {
  if (printedTotal !== null) {
    const padded = number.padStart(3, "0");
    const q = `(number:"${number}" OR number:"${padded}") set.printedTotal:${printedTotal}`;
    const cards = await tcgQuery(q);
    const exact = cards.find((c) => c.set.printedTotal === printedTotal && sameNumber(c.number, number));
    if (exact) return normalize(exact);
    const sameTotal = cards.find((c) => c.set.printedTotal === printedTotal);
    return sameTotal ? normalize(sameTotal) : null;
  }
  // Only the numerator was read — ambiguous across sets. Best-effort: newest set.
  const candidates = await tcgQuery(`number:"${number}"`);
  return candidates[0] ? normalize(candidates[0]) : null;
}

export async function getCardById(id: string): Promise<Card | null> {
  const res = await fetch(`${TCG_API}/cards/${encodeURIComponent(id)}`, { headers: headers() });
  if (!res.ok) return null;
  const json = (await res.json()) as { data?: TcgCard };
  return json.data ? normalize(json.data) : null;
}

/** Pick the most "general" market price — prefer normal/holo over special variants. */
export function pickGeneralPrice(card: Card): MarketPrice | null {
  if (!card.prices.length) return null;
  const priority: PriceVariant[] = [
    "normal",
    "holofoil",
    "reverseHolofoil",
    "1stEditionNormal",
    "1stEditionHolofoil"
  ];
  for (const variant of priority) {
    const hit = card.prices.find((p) => p.variant === variant && p.marketUsd !== null);
    if (hit) return hit;
  }
  return card.prices.find((p) => p.marketUsd !== null) ?? card.prices[0];
}
