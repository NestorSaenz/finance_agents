"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "safi:newDesign";

/** Build-time default (NEXT_PUBLIC_RESUMEN_V2=true turns the redesign on for everyone). */
export const NEW_DESIGN_DEFAULT = process.env.NEXT_PUBLIC_RESUMEN_V2 === "true";

/** The persisted choice, or null when absent / storage is unavailable. */
function readStored(storage: Pick<Storage, "getItem"> | null): boolean | null {
  try {
    const value = storage?.getItem(STORAGE_KEY);
    return value === "1" ? true : value === "0" ? false : null;
  } catch {
    return null;
  }
}

function writeStored(storage: Pick<Storage, "setItem"> | null, on: boolean): void {
  try {
    storage?.setItem(STORAGE_KEY, on ? "1" : "0");
  } catch {
    // Private mode / blocked storage: the switch simply is not persisted.
  }
}

function safeStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/**
 * Resolve the switch: `?nuevo=1|0` in the URL wins (and is persisted), then the
 * stored choice, then `fallback`. Pure so it can be tested without a browser.
 */
export function resolveNewDesign(
  search: string,
  storage: Pick<Storage, "getItem" | "setItem"> | null,
  fallback: boolean,
): boolean {
  const param = new URLSearchParams(search).get("nuevo");
  if (param === "1" || param === "0") {
    const on = param === "1";
    writeStored(storage, on);
    return on;
  }
  return readStored(storage) ?? fallback;
}

/**
 * Whether the redesigned screens are on. Off by default. Read on the client after
 * mount, so the first render matches the server (no hydration mismatch).
 */
export function useNewDesign(): boolean {
  const [on, setOn] = useState<boolean>(NEW_DESIGN_DEFAULT);
  useEffect(() => {
    setOn(resolveNewDesign(window.location.search, safeStorage(), NEW_DESIGN_DEFAULT));
  }, []);
  return on;
}
