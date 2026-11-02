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
  return iraqiMobileE164(raw) !== null;
}

/** `0770 123 4567` / `+964…` / Arabic-Indic digits → `+9647701234567`, or null. Used to compare
 * a typed number with the server's (already normalised) verified phone. */
export function iraqiMobileE164(raw: string): string | null {
  let v = toLatinDigits(raw).replace(/[^\d+]/g, "");
  if (v.startsWith("00")) v = "+" + v.slice(2);
  if (v.startsWith("+964")) v = "0" + v.slice(4);
  if (v.length === 10 && v.startsWith("7")) v = "0" + v;
  return /^07[3-9]\d{8}$/.test(v) ? `+964${v.slice(1)}` : null;
}

/** `+9647701234567` → `07701234567` for display in inputs. */
export function localIraqiPhone(e164: string): string {
  return e164.startsWith("+964") ? `0${e164.slice(4)}` : e164;
}
