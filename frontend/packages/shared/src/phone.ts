const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";
const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

export function toLatinDigits(value: string): string {
  return value.replace(/[٠-٩۰-۹]/g, (d) => {
    const i = ARABIC_DIGITS.indexOf(d);
    return String(i >= 0 ? i : PERSIAN_DIGITS.indexOf(d));
  });
}

/** Client-side hint only — the server validates and normalises authoritatively. */
export function looksLikeIraqiMobile(raw: string): boolean {
  let v = toLatinDigits(raw).replace(/[^\d+]/g, "");
  if (v.startsWith("00")) v = "+" + v.slice(2);
  if (v.startsWith("+964")) v = "0" + v.slice(4);
  if (v.length === 10 && v.startsWith("7")) v = "0" + v;
  return /^07[3-9]\d{8}$/.test(v);
}
