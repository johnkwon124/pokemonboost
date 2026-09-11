/**
 * EUR→USD rate for showing Cardmarket (EU) prices in USD. Fetched once per
 * session from frankfurter.app (free, no key, CORS); falls back to a rough
 * constant if the fetch fails so the UI can still label an approximate value.
 */

export const FALLBACK_EUR_USD = 1.1;

let ratePromise: Promise<number> | null = null;

export function eurToUsdRate(): Promise<number> {
  if (!ratePromise) {
    ratePromise = fetch("https://api.frankfurter.app/latest?from=EUR&to=USD")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: { rates?: { USD?: number } }) =>
        typeof j?.rates?.USD === "number" ? j.rates.USD : FALLBACK_EUR_USD
      )
      .catch(() => {
        ratePromise = null; // allow a retry next call
        return FALLBACK_EUR_USD;
      });
  }
  return ratePromise;
}
