import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Not using Vitest globals, so wire React Testing Library's cleanup manually
// (otherwise renders accumulate across tests in the same file).
afterEach(() => cleanup());

// jsdom doesn't implement scrollIntoView (used by ChatView auto-scroll).
Element.prototype.scrollIntoView = vi.fn();
