import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CalendarGrid } from "@/components/CalendarGrid";
import type { DailyCustodyState } from "@/lib/types";
import { PARENT_A, PARENT_B } from "@/lib/types";

const days: DailyCustodyState[] = [
  {
    current_date: "2026-01-05",
    baseline_parent: PARENT_A,
    final_parent: PARENT_A,
    is_overridden: false,
  },
  {
    current_date: "2026-01-06",
    baseline_parent: PARENT_A,
    final_parent: PARENT_B,
    is_overridden: true,
  },
];

describe("CalendarGrid", () => {
  it("renders one cell per schedule day", () => {
    render(<CalendarGrid days={days} monthStartDate="2026-01-05" />);
    expect(screen.getAllByRole("gridcell")).toHaveLength(2);
  });

  it("uses compact gaps and single-letter weekday headers on base viewport", () => {
    const { container } = render(
      <CalendarGrid days={days} monthStartDate="2026-01-05" />,
    );
    const grids = container.querySelectorAll(".grid.grid-cols-7");
    expect(grids).toHaveLength(2);
    for (const grid of grids) {
      expect(grid.className).toMatch(/\bgap-1\b/);
    }
    expect(screen.getByText("Sun")).toBeInTheDocument();
    expect(screen.getByText("Mon")).toBeInTheDocument();
    const shortLabels = container.querySelectorAll(".sm\\:hidden");
    expect(shortLabels).toHaveLength(7);
    expect([...shortLabels].map((el) => el.textContent)).toEqual([
      "S",
      "M",
      "T",
      "W",
      "T",
      "F",
      "S",
    ]);
  });
});
