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
});
