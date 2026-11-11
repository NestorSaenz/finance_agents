import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveNewDesign, useNewDesign } from "@/lib/useNewDesign";

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    data,
  };
}

const throwing = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
};

describe("resolveNewDesign", () => {
  it("defaults to the fallback (off)", () => {
    expect(resolveNewDesign("", memoryStorage(), false)).toBe(false);
    expect(resolveNewDesign("?otro=1", memoryStorage(), false)).toBe(false);
  });

  it("the query param wins and is persisted", () => {
    const storage = memoryStorage();
    expect(resolveNewDesign("?nuevo=1", storage, false)).toBe(true);
    expect(storage.data.get("safi:newDesign")).toBe("1");
    // Later visits without the param keep it on.
    expect(resolveNewDesign("", storage, false)).toBe(true);
  });

  it("?nuevo=0 turns it off, even when stored or defaulted on", () => {
    const storage = memoryStorage({ "safi:newDesign": "1" });
    expect(resolveNewDesign("?nuevo=0", storage, true)).toBe(false);
    expect(storage.data.get("safi:newDesign")).toBe("0");
    expect(resolveNewDesign("", storage, true)).toBe(false);
  });

  it("ignores other values of the param", () => {
    expect(resolveNewDesign("?nuevo=si", memoryStorage(), false)).toBe(false);
  });

  it("a storage that throws never breaks: the param still applies, otherwise the fallback", () => {
    expect(resolveNewDesign("?nuevo=1", throwing, false)).toBe(true);
    expect(resolveNewDesign("", throwing, false)).toBe(false);
    expect(resolveNewDesign("", null, true)).toBe(true);
  });
});

describe("useNewDesign", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState(null, "", "/");
  });
  afterEach(() => vi.restoreAllMocks());

  it("is off by default", () => {
    const { result } = renderHook(() => useNewDesign());
    expect(result.current).toBe(false);
  });

  it("reads ?nuevo=1 after mount and persists it", () => {
    window.history.replaceState(null, "", "/?nuevo=1");
    const { result } = renderHook(() => useNewDesign());
    expect(result.current).toBe(true);
    expect(window.localStorage.getItem("safi:newDesign")).toBe("1");
  });

  it("?nuevo=0 turns a persisted switch off", () => {
    window.localStorage.setItem("safi:newDesign", "1");
    window.history.replaceState(null, "", "/?nuevo=0");
    const { result } = renderHook(() => useNewDesign());
    expect(result.current).toBe(false);
  });

  it("does not break when localStorage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    window.history.replaceState(null, "", "/?nuevo=1");
    const { result } = renderHook(() => useNewDesign());
    expect(result.current).toBe(true);
  });
});
