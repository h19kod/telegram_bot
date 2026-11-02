import { describe, expect, it } from "vitest";

import { formatMoney } from "./format";
import { iraqiMobileE164, localIraqiPhone, looksLikeIraqiMobile, toLatinDigits } from "./phone";

describe("formatMoney", () => {
  it("formats IQD without decimals", () => {
    expect(formatMoney(12500, "IQD", "ar")).toBe("12,500 د.ع");
    expect(formatMoney(12500, "IQD", "en")).toBe("IQD 12,500");
  });
  it("formats USD minor units", () => {
    expect(formatMoney(1250, "USD", "en")).toBe("$12.50");
  });
});

describe("phone", () => {
  it.each(["07701234567", "0770 123 4567", "+9647701234567", "009647701234567", "7701234567",
    "٠٧٧٠١٢٣٤٥٦٧"])("accepts %s", (v) => expect(looksLikeIraqiMobile(v)).toBe(true));
  it.each(["", "0770123", "06701234567", "abc"])("rejects %s",
    (v) => expect(looksLikeIraqiMobile(v)).toBe(false));
  it("converts Arabic-Indic digits", () => expect(toLatinDigits("٠١٢٣")).toBe("0123"));
  it("normalises to E.164 like the server", () => {
    expect(iraqiMobileE164("0770 123 4567")).toBe("+9647701234567");
    expect(iraqiMobileE164("٠٧٨٠١١١٢٢٣٣")).toBe("+9647801112233");
    expect(iraqiMobileE164("009647701234567")).toBe("+9647701234567");
    expect(iraqiMobileE164("0770")).toBeNull();
    expect(localIraqiPhone("+9647701234567")).toBe("07701234567");
  });
});
