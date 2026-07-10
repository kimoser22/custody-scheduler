import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DayCell } from "@/components/DayCell";
import type { DailyCustodyState } from "@/lib/types";
import { PARENT_A, PARENT_B } from "@/lib/types";

const baseDay: DailyCustodyState = {
  current_date: "2026-01-05",
  baseline_parent: PARENT_A,
  final_parent: PARENT_A,
  is_overridden: false,
};

describe("DayCell", () => {
  it("renders the day and parent assignment", () => {
    render(<DayCell day={baseDay} />);
    expect(screen.getByRole("gridcell")).toHaveTextContent("05");
    expect(screen.getByRole("gridcell")).toHaveTextContent(PARENT_A);
  });

  it("applies parent-specific styling class", () => {
    render(<DayCell day={{ ...baseDay, final_parent: PARENT_B }} />);
    expect(screen.getByRole("gridcell")).toHaveAttribute("data-parent", "parent-b");
  });

  it("highlights overridden days", () => {
    render(
      <DayCell
        day={{
          ...baseDay,
          is_overridden: true,
          final_parent: PARENT_B,
          override_details: {
            override_date: "2026-01-05",
            assigned_parent: PARENT_B,
            override_type: "Holiday",
            description: "Holiday",
            is_active: true,
            status: "Approved",
          },
        }}
      />,
    );

    expect(screen.getByRole("gridcell")).toHaveAttribute("data-overridden", "true");
    expect(screen.getByText("Override")).toBeInTheDocument();
  });

  it("calls onSelect when clicked", async () => {
    const onSelect = vi.fn();
    const user = (await import("@testing-library/user-event")).default;
    render(<DayCell day={baseDay} onSelect={onSelect} />);
    await user.click(screen.getByRole("gridcell"));
    expect(onSelect).toHaveBeenCalledWith(baseDay);
  });
});
