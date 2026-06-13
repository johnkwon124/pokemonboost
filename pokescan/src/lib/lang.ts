/**
 * Detect the language of a Pokemon card from raw OCR text. Japanese and Korean
 * cards print their collector number in Latin digits (e.g. "025/078"), but the
 * surrounding text — illustrator credit, set names — uses Hiragana/Katakana or
 * Hangul respectively, which gives a reliable language signal even from just
 * the bottom band of the card.
 */
export type CardLang = "ja" | "ko" | "en";

// Hangul syllables U+AC00..U+D7A3
const HANGUL = /[가-힣]/;
// Hiragana U+3040..U+309F and Katakana U+30A0..U+30FF
const HIRAGANA_KATAKANA = /[぀-ヿ]/;

export function detectCardLang(text: string): CardLang {
  if (!text) return "en";
  if (HANGUL.test(text)) return "ko";
  if (HIRAGANA_KATAKANA.test(text)) return "ja";
  return "en";
}

export function langLabel(lang: CardLang): string {
  switch (lang) {
    case "ja":
      return "일본어";
    case "ko":
      return "한국어";
    default:
      return "영문";
  }
}
