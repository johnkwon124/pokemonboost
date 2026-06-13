export type PriceVariant =
  | "normal"
  | "holofoil"
  | "reverseHolofoil"
  | "1stEditionHolofoil"
  | "1stEditionNormal";

export interface MarketPrice {
  variant: PriceVariant;
  marketUsd: number | null;
  lowUsd: number | null;
  midUsd: number | null;
  highUsd: number | null;
  updatedAt: string | null;
  source: string;
}

export interface Card {
  id: string;
  name: string;
  number: string;
  setId: string;
  setName: string;
  setSeries: string | null;
  setPrintedTotal: number | null;
  releaseDate: string | null;
  rarity: string | null;
  supertype: string | null;
  subtypes: string[];
  types: string[];
  hp: string | null;
  imageSmall: string | null;
  imageLarge: string | null;
  attacks: {
    name: string;
    cost: string[];
    damage: string;
    text: string;
  }[];
  weaknesses: { type: string; value: string }[];
  resistances: { type: string; value: string }[];
  flavorText: string | null;
  artist: string | null;
  prices: MarketPrice[];
  // "en" English / "jp" Japanese / "kr" Korean — drives data source and labels
  locale: "en" | "jp" | "kr";
  estimated: boolean; // true if price was inferred from the English equivalent
}

export interface Analysis {
  rarityNote: string;
  setContext: string;
  collectibility: string;
  investment: string;
  source: "tcg-api" | "claude";
}

/** In-memory only — a card the user scanned during the current session. */
export interface SessionScan {
  key: string;
  card: Card;
  analysis: Analysis | null;
  at: number;
}
