export type Lang = "ar" | "en";

const EXPONENT: Record<string, number> = { IQD: 0, USD: 2 };
const SYMBOL: Record<string, Record<Lang, string>> = {
  IQD: { ar: "د.ع", en: "IQD" },
  USD: { ar: "$", en: "$" },
};

/** Format integer minor units. Server is the only source of amounts; this only displays. */
export function formatMoney(amount: number, currency: string, lang: Lang): string {
  const exp = EXPONENT[currency] ?? 0;
  const value = amount / 10 ** exp;
  const num = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: exp,
    maximumFractionDigits: exp,
  }).format(Math.abs(value));
  const sign = amount < 0 ? "-" : "";
  const sym = SYMBOL[currency]?.[lang] ?? currency;
  if (currency === "USD") return `${sign}${sym}${num}`;
  return lang === "ar" ? `${sign}${num} ${sym}` : `${sign}${sym} ${num}`;
}

export function formatDateTime(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === "ar" ? "ar-IQ" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Baghdad",
    numberingSystem: "latn",
  }).format(new Date(iso));
}

export function formatTime(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === "ar" ? "ar-IQ" : "en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Baghdad",
    numberingSystem: "latn",
  }).format(new Date(iso));
}
