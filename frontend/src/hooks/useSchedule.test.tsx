import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useSchedule } from "@/hooks/useSchedule";
import type { DailyCustodyState } from "@/lib/types";
import { PARENT_A } from "@/lib/types";

function ScheduleProbe({
  fetchSchedule,
}: {
  fetchSchedule: typeof defaultFetch;
}) {
  const { days, isLoading, error } = useSchedule({
    startDate: "2026-01-01",
    endDate: "2026-01-14",
    authToken: "viewer:dev",
    fetchSchedule,
  });

  if (isLoading) {
    return <p>Loading schedule...</p>;
  }

  if (error) {
    return <p>{error}</p>;
  }

  return <p>{days.length} days loaded</p>;
}

const mockDays: DailyCustodyState[] = [
  {
    current_date: "2026-01-01",
    baseline_parent: PARENT_A,
    final_parent: PARENT_A,
    is_overridden: false,
  },
];

async function defaultFetch() {
  return mockDays;
}

describe("useSchedule", () => {
  it("loads schedule data for the requested date range", async () => {
    const fetchSchedule = vi.fn(async () => mockDays);

    render(<ScheduleProbe fetchSchedule={fetchSchedule} />);

    expect(screen.getByText("Loading schedule...")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("1 days loaded")).toBeInTheDocument();
    });

    expect(fetchSchedule).toHaveBeenCalledWith({
      start_date: "2026-01-01",
      end_date: "2026-01-14",
    });
  });

  it("surfaces an error message when fetch fails", async () => {
    const fetchSchedule = vi.fn(async () => {
      throw new Error("Failed to load schedule.");
    });

    render(<ScheduleProbe fetchSchedule={fetchSchedule} />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load schedule.")).toBeInTheDocument();
    });
  });
});
