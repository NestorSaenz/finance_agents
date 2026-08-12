import { describe, expect, it } from "vitest";

import { categoryLabel, formatMoney } from "./format";

describe("categoryLabel", () => {
  it("maps known slugs to Spanish labels", () => {
    expect(categoryLabel("alimentacion")).toBe("Alimentación");
    expect(categoryLabel("restaurantes")).toBe("Restaurantes");
  });

  it("capitalizes unknown slugs as a fallback", () => {
    expect(categoryLabel("misc")).toBe("Misc");
  });
});

describe("formatMoney", () => {
  it("formats decimal strings as currency without decimals", () => {
    // Non-breaking spaces / symbol placement vary by ICU; assert on the digits.
    expect(formatMoney("50000")).toMatch(/50.?000/);
  });

  it("defaults to COP (a zero-decimal currency): no cents", () => {
    // COP is zero-decimal, so a 1000 amount renders with no fractional part.
    const cop = formatMoney(1000, "COP");
    expect(cop).toContain("$");
    expect(cop).not.toMatch(/[.,]\d{2}\b/); // no ",00"/".00" cents
  });

  it("respects the currency: USD keeps two decimals", () => {
    // USD is not zero-decimal, so Intl adds the two-decimal minor unit.
    const usd = formatMoney(1000, "USD");
    expect(usd).toContain("$");
    expect(usd).toMatch(/[.,]\d{2}\b/); // has cents (e.g. "1000,00")
    // The currency actually changes the output vs the zero-decimal default.
    expect(usd).not.toBe(formatMoney(1000, "COP"));
  });

  it("returns a dash for non-numeric input", () => {
    expect(formatMoney("abc")).toBe("—");
  });
});
