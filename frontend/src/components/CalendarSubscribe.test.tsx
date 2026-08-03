import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CalendarSubscribe } from "@/components/CalendarSubscribe";
import type { EnsureCalendarFeed } from "@/lib/api/calendarFeed";

describe("CalendarSubscribe", () => {
  it("creates and copies a subscribe URL", async () => {
    const user = userEvent.setup();
    const ensureCalendarFeed = vi.fn<EnsureCalendarFeed>(async ({ rotate } = {}) => ({
      ok: true,
      data: {
        token: rotate ? "new-token" : "tok-123",
        url: rotate
          ? "https://api.example/api/v1/schedule/feed.ics?token=new-token"
          : "https://api.example/api/v1/schedule/feed.ics?token=tok-123",
      },
    }));

    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(<CalendarSubscribe ensureCalendarFeed={ensureCalendarFeed} />);

    await user.click(screen.getByRole("button", { name: "Create link" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Subscribe URL")).toHaveValue(
        "https://api.example/api/v1/schedule/feed.ics?token=tok-123",
      );
    });
    expect(ensureCalendarFeed).toHaveBeenCalledWith({ rotate: false });

    await user.click(screen.getByRole("button", { name: "Copy link" }));
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(
        "https://api.example/api/v1/schedule/feed.ics?token=tok-123",
      );
    });
    expect(screen.getByText("Copied subscribe URL.")).toBeInTheDocument();
  });

  it("shows API errors from mint", async () => {
    const user = userEvent.setup();
    const ensureCalendarFeed = vi.fn<EnsureCalendarFeed>(async () => ({
      ok: false,
      status: 401,
      detail: "Not authenticated",
    }));

    render(<CalendarSubscribe ensureCalendarFeed={ensureCalendarFeed} />);
    await user.click(screen.getByRole("button", { name: "Create link" }));

    await waitFor(() => {
      expect(screen.getByText("Not authenticated")).toBeInTheDocument();
    });
  });
});
