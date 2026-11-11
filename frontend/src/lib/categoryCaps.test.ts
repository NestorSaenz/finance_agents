import { describe, expect, it } from "vitest";

import {
  canCreate,
  capPct,
  capsSummary,
  filterCategories,
  normalizeCategory,
  normalizeText,
} from "@/lib/categoryCaps";

describe("capsSummary", () => {
  it("counts chosen categories, sums the amounts and gives the % of income", () => {
    const s = capsSummary(["a", "b", "c"], { a: "2000000", b: "1.500.000" }, 14350000);
    expect(s.count).toBe(3); // "c" has no amount yet
    expect(s.total).toBe(3500000);
    expect(s.pct).toBe(24.4);
  });

  it("pct is null without a usable income", () => {
    for (const income of [0, null, undefined, Number.NaN, -5]) {
      expect(capsSummary(["a"], { a: "100" }, income).pct).toBeNull();
    }
  });

  it("an empty selection is zero", () => {
    expect(capsSummary([], {}, 1000)).toEqual({ count: 0, total: 0, pct: 0 });
  });

  it("can exceed 100%", () => {
    expect(capsSummary(["a"], { a: "1500" }, 1000).pct).toBe(150);
  });
});

describe("capPct", () => {
  it("is one decimal or null", () => {
    expect(capPct(2000000, 14350000)).toBe(13.9);
    expect(capPct(5, 0)).toBeNull();
  });
});

describe("filterCategories", () => {
  const all = ["alimentacion", "transporte", "educacion", "jardineria"];

  it("matches without accents or case, by label or slug", () => {
    expect(filterCategories("ALIMENTACIÓN", all, [])).toEqual(["alimentacion"]);
    expect(filterCategories("educ", all, [])).toEqual(["educacion"]);
    expect(filterCategories("trans", all, [])).toEqual(["transporte"]);
  });

  it("excludes the chosen ones; an empty query lists the rest", () => {
    expect(filterCategories("", all, ["transporte"])).toEqual([
      "alimentacion",
      "educacion",
      "jardineria",
    ]);
    expect(filterCategories("transp", all, ["transporte"])).toEqual([]);
  });
});

describe("canCreate", () => {
  const all = ["alimentacion", "jardineria"];

  it("is true only for text that matches no category exactly", () => {
    expect(canCreate("colegio", all)).toBe(true);
    expect(canCreate("jardin", all)).toBe(true); // partial match is not exact
  });

  it("is false for exact matches regardless of accents/case, and for empty text", () => {
    expect(canCreate("Alimentación", all)).toBe(false);
    expect(canCreate("JARDINERIA", all)).toBe(false);
    expect(canCreate("   ", all)).toBe(false);
    expect(canCreate("", all)).toBe(false);
  });
});

describe("normalizeCategory / normalizeText", () => {
  it("normalizes a new category like the wizard always did", () => {
    expect(normalizeCategory("  Jardinería   Verde ")).toBe("jardinería verde");
  });
  it("strips accents for matching", () => {
    expect(normalizeText(" Educación ")).toBe("educacion");
  });
});
