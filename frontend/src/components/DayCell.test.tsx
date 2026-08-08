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
  it("renders an unpadded day and short parent label", () => {
    render(<DayCell day={baseDay} />);
    const cell = screen.getByRole("gridcell");
    expect(cell).toHaveTextContent("5");
    expect(cell).not.toHaveTextContent("05");
    expect(cell).toHaveTextContent("A");
    expect(cell).not.toHaveTextContent("Parent A");
    expect(cell.className).toMatch(/p-1/);
    expect(cell.className).toMatch(/text-xs/);
  });

  it("exposes the full parent and date in the accessible name", () => {
    render(<DayCell day={baseDay} />);
    expect(
      screen.getByRole("gridcell", { name: /2026-01-05.*Parent A/i }),
    ).toBeInTheDocument();
  });

  it("applies parent-specific styling class", () => {
    render(<DayCell day={{ ...baseDay, final_parent: PARENT_B }} />);
    expect(screen.getByRole("gridcell")).toHaveAttribute("data-parent", "parent-b");
    expect(screen.getByRole("gridcell")).toHaveTextContent("B");
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

    const cell = screen.getByRole("gridcell");
    expect(cell).toHaveAttribute("data-overridden", "true");
    expect(screen.getByText("Holiday")).toBeInTheDocument();
    expect(screen.getByText("Holiday").className).toMatch(/line-clamp-1/);
  });

  it("shows Holiday badge when type is Holiday and description is empty", () => {
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
            description: "   ",
            is_active: true,
            status: "Approved",
          },
        }}
      />,
    );
    expect(screen.getByText("Holiday")).toBeInTheDocument();
  });

  it("prefers a short description on the override badge", () => {
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
            description: "Spring break",
            is_active: true,
            status: "Approved",
          },
        }}
      />,
    );
    expect(screen.getByText("Spring break")).toBeInTheDocument();
  });

  it("calls onSelect when clicked", async () => {
    const onSelect = vi.fn();
    const user = (await import("@testing-library/user-event")).default;
    render(<DayCell day={baseDay} onSelect={onSelect} />);
    await user.click(screen.getByRole("gridcell"));
    expect(onSelect).toHaveBeenCalledWith(baseDay);
  });
});
