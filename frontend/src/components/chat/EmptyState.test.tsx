import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("links to the public guide", () => {
    render(<EmptyState onPick={() => {}} />);

    const link = screen.getByRole("link", { name: /Ver la guía/i });
    expect(link).toHaveAttribute("href", "/guia");
  });
});
