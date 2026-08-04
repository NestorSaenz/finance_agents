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

  it("returns a dash for non-numeric input", () => {
    expect(formatMoney("abc")).toBe("—");
  });
});
