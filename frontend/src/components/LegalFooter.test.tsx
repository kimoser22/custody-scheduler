import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LegalFooter } from "@/components/LegalFooter";

describe("LegalFooter", () => {
  it("links to privacy and terms pages", () => {
    render(<LegalFooter />);

    const privacy = screen.getByRole("link", { name: /privacy/i });
    const terms = screen.getByRole("link", { name: /terms/i });

    expect(privacy).toHaveAttribute("href", "/privacy");
    expect(terms).toHaveAttribute("href", "/terms");
  });
});
