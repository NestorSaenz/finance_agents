import { describe, expect, it } from "vitest";

import {
  digitsFromPaste,
  digitsOnly,
  formatAmountInput,
  formatWithCaret,
  parseAmountInput,
} from "@/lib/moneyInput";

describe("formatAmountInput", () => {
  it("always groups thousands, 4 digits included (Intl es would not)", () => {
    expect(formatAmountInput("1500000")).toBe("1.500.000");
    expect(formatAmountInput("1500")).toBe("1.500");
    expect(formatAmountInput("999")).toBe("999");
    expect(formatAmountInput("12000")).toBe("12.000");
  });

  it("cleans pasted and spaced text", () => {
    expect(formatAmountInput("$1.500.000")).toBe("1.500.000");
    expect(formatAmountInput("1,500,000")).toBe("1.500.000");
    expect(formatAmountInput(" 1 500 000 ")).toBe("1.500.000");
  });

  it("empty and non-numeric give an empty string; leading zeros are dropped", () => {
    expect(formatAmountInput("")).toBe("");
    expect(formatAmountInput("abc")).toBe("");
    expect(formatAmountInput("007")).toBe("7");
    expect(formatAmountInput("0")).toBe("0");
  });
});

describe("parseAmountInput", () => {
  it("parses formatted, pasted and spaced amounts", () => {
    expect(parseAmountInput("1.500.000")).toBe(1500000);
    expect(parseAmountInput("$1.500.000")).toBe(1500000);
    expect(parseAmountInput("1,500,000")).toBe(1500000);
    expect(parseAmountInput(" 2 000 ")).toBe(2000);
  });

  it("empty or no digits is 0", () => {
    expect(parseAmountInput("")).toBe(0);
    expect(parseAmountInput("abc")).toBe(0);
  });

  it("round-trips with format", () => {
    for (const n of [0, 5, 999, 1000, 1500, 12345, 1500000, 14350000]) {
      expect(parseAmountInput(formatAmountInput(String(n)))).toBe(n);
    }
  });
});

describe("digitsFromPaste", () => {
  it("drops a trailing decimal part of pasted amounts", () => {
    expect(digitsFromPaste("1.500,50")).toBe("1500");
    expect(digitsFromPaste("$1,500.5")).toBe("1500");
    expect(digitsFromPaste("1.500.000")).toBe("1500000");
    expect(digitsFromPaste("  $ 2.000 ")).toBe("2000");
  });

  it("typing never uses it: '1.50' (one digit deleted from '1.500') stays 150", () => {
    expect(digitsOnly("1.50")).toBe("150");
  });
});

describe("formatWithCaret", () => {
  it("keeps the caret after the same digit when a separator appears", () => {
    // "1500" shown as "1.500"; typing "0" at the end of "1.500" -> raw "1.5000".
    const next = formatWithCaret("1.5000", 6);
    expect(next.text).toBe("15.000");
    expect(next.caret).toBe(6);
  });

  it("keeps the caret in the middle of the number", () => {
    // Typed "9" after the first digit of "1.500": raw "19.500", caret 2.
    const next = formatWithCaret("19.500", 2);
    expect(next.text).toBe("19.500");
    expect(next.caret).toBe(2);
    // Typed "9" after "1.5" of "1.500": raw "1.5900", caret 4 -> digits before: 1,5,9 = 3.
    const mid = formatWithCaret("1.5900", 4);
    expect(mid.text).toBe("15.900");
    expect(mid.caret).toBe(4); // after "15.9" (digits 1,5,9)
  });

  it("handles empty input and a caret at 0", () => {
    expect(formatWithCaret("", 0)).toEqual({ text: "", caret: 0 });
    expect(formatWithCaret("1500", 0)).toEqual({ text: "1.500", caret: 0 });
  });
});

describe("limitDigits / backspaceOverSeparator", () => {
  it("keeps at most 10 digits", async () => {
    const { limitDigits, MAX_AMOUNT_DIGITS } = await import("@/lib/moneyInput");
    expect(MAX_AMOUNT_DIGITS).toBe(10);
    expect(limitDigits("123456789012")).toBe("1234567890");
    expect(limitDigits("$1.500")).toBe("1500");
  });

  it("removes the digit before a separator the caret sits right after", async () => {
    const { backspaceOverSeparator } = await import("@/lib/moneyInput");
    expect(backspaceOverSeparator("1.500", 2)).toEqual({ raw: "500", caret: 0 });
    expect(backspaceOverSeparator("12.500", 3)).toEqual({ raw: "1500", caret: 1 });
    expect(backspaceOverSeparator("1.500", 3)).toBeNull(); // not after a separator
    expect(backspaceOverSeparator("1.500", 0)).toBeNull();
  });
});
