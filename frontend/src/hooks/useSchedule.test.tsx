import { render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { useSchedule } from "@/hooks/useSchedule";
import type { FetchSchedule } from "@/lib/api/schedule";
import type { DailyCustodyState } from "@/lib/types";
import { PARENT_A, PARENT_B } from "@/lib/types";

function dayFor(date: string, parent = PARENT_A): DailyCustodyState {
  return {
    current_date: date,
    baseline_parent: parent,
    final_parent: parent,
    is_overridden: false,
  };
}

const JAN = [dayFor("2026-01-01")];
const FEB = [dayFor("2026-02-01", PARENT_B), dayFor("2026-02-02", PARENT_B)];

const JAN_RANGE = { startDate: "2026-01-01", endDate: "2026-01-31" };
const FEB_RANGE = { startDate: "2026-02-01", endDate: "2026-02-28" };

/**
 * Drives useSchedule with switchable range + a refetch/prefetch trigger so a
 * test can navigate months and force revalidation the way the page does.
 */
function ScheduleProbe({
  fetchSchedule,
  initialRange = JAN_RANGE,
}: {
  fetchSchedule: FetchSchedule;
  initialRange?: { startDate: string; endDate: string };
}) {
  const [range, setRange] = useState(initialRange);
  const { days, isLoading, error, refetch, prefetch } = useSchedule({
    startDate: range.startDate,
    endDate: range.endDate,
    authToken: "viewer:dev",
    fetchSchedule,
  });

  return (
    <div>
      <p data-testid="state">
        {isLoading ? "loading" : error ? `error:${error}` : `days:${days.length}`}
      </p>
      <button onClick={() => setRange(FEB_RANGE)}>go feb</button>
      <button onClick={() => setRange(JAN_RANGE)}>go jan</button>
      <button onClick={() => void refetch()}>refetch</button>
      <button onClick={() => void prefetch(FEB_RANGE)}>prefetch feb</button>
    </div>
  );
}

function state(): string {
  return screen.getByTestId("state").textContent ?? "";
}

describe("useSchedule", () => {
  it("loads schedule data for the requested date range (cold path)", async () => {
    const fetchSchedule = vi.fn<FetchSchedule>(async () => JAN);

    render(<ScheduleProbe fetchSchedule={fetchSchedule} />);

    expect(state()).toBe("loading");
    await waitFor(() => expect(state()).toBe("days:1"));
    expect(fetchSchedule).toHaveBeenCalledWith({
      start_date: "2026-01-01",
      end_date: "2026-01-31",
    });
  });

  it("surfaces an error on a cold fetch failure", async () => {
    const fetchSchedule = vi.fn<FetchSchedule>(async () => {
      throw new Error("Failed to load schedule.");
    });

    render(<ScheduleProbe fetchSchedule={fetchSchedule} />);

    await waitFor(() => expect(state()).toBe("error:Failed to load schedule."));
  });

  it("shows a revisited month instantly with no loading flash", async () => {
    const byRange: Record<string, DailyCustodyState[]> = {
      "2026-01-01": JAN,
      "2026-02-01": FEB,
    };
    const fetchSchedule = vi.fn<FetchSchedule>(
      async ({ start_date }) => byRange[start_date] ?? [],
    );
    const user = (await import("@testing-library/user-event")).default.setup();

    render(<ScheduleProbe fetchSchedule={fetchSchedule} />);
    await waitFor(() => expect(state()).toBe("days:1")); // Jan cold

    await user.click(screen.getByText("go feb"));
    await waitFor(() => expect(state()).toBe("days:2")); // Feb cold

    // Back to Jan: it is cached, so it must render immediately without ever
    // flipping to "loading". Poll a few frames to prove no flash occurred.
    await user.click(screen.getByText("go jan"));
    for (let i = 0; i < 5; i += 1) {
      expect(state()).not.toBe("loading");
    }
    expect(state()).toBe("days:1");
  });

  it("revalidates a cached range in the background", async () => {
    const fetchSchedule = vi.fn<FetchSchedule>(async () => JAN);
    const user = (await import("@testing-library/user-event")).default.setup();

    render(<ScheduleProbe fetchSchedule={fetchSchedule} />);
    await waitFor(() => expect(state()).toBe("days:1"));
    await user.click(screen.getByText("go feb"));
    await waitFor(() => expect(state()).toBe("days:1")); // FEB mock also returns JAN len 1

    const callsBefore = fetchSchedule.mock.calls.length;
    await user.click(screen.getByText("go jan")); // cached
    await waitFor(() =>
      expect(fetchSchedule.mock.calls.length).toBe(callsBefore + 1),
    );
  });

  it("prefetch warms the cache so a later switch is instant", async () => {
    const fetchSchedule = vi.fn<FetchSchedule>(async ({ start_date }) =>
      start_date === "2026-02-01" ? FEB : JAN,
    );
    const user = (await import("@testing-library/user-event")).default.setup();

    render(<ScheduleProbe fetchSchedule={fetchSchedule} />);
    await waitFor(() => expect(state()).toBe("days:1"));

    await user.click(screen.getByText("prefetch feb"));
    await waitFor(() =>
      expect(
        fetchSchedule.mock.calls.some((c) => c[0].start_date === "2026-02-01"),
      ).toBe(true),
    );

    // Now navigating to Feb is a cache hit — never shows loading.
    await user.click(screen.getByText("go feb"));
    for (let i = 0; i < 5; i += 1) {
      expect(state()).not.toBe("loading");
    }
    expect(state()).toBe("days:2");
  });

  it("refetch re-fetches the current range even when cached", async () => {
    const fetchSchedule = vi.fn<FetchSchedule>(async () => JAN);
    const user = (await import("@testing-library/user-event")).default.setup();

    render(<ScheduleProbe fetchSchedule={fetchSchedule} />);
    await waitFor(() => expect(state()).toBe("days:1"));

    const before = fetchSchedule.mock.calls.length;
    await user.click(screen.getByText("refetch"));
    await waitFor(() =>
      expect(fetchSchedule.mock.calls.length).toBe(before + 1),
    );
  });

  it("keeps stale data when a background revalidation fails", async () => {
    let calls = 0;
    const fetchSchedule = vi.fn<FetchSchedule>(async () => {
      calls += 1;
      if (calls === 1) {
        return JAN; // cold load succeeds
      }
      throw new Error("network blip"); // revalidation fails
    });
    const user = (await import("@testing-library/user-event")).default.setup();

    render(<ScheduleProbe fetchSchedule={fetchSchedule} />);
    await waitFor(() => expect(state()).toBe("days:1"));

    await user.click(screen.getByText("refetch")); // triggers the failing fetch
    // Data stays; no blank, no error surfaced over a populated grid.
    await waitFor(() => expect(calls).toBe(2));
    expect(state()).toBe("days:1");
  });
});
