import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PendingOverrides } from "@/components/PendingOverrides";
import type { DecideOverride, FetchPendingOverrides } from "@/lib/api/schedule";
import type { ScheduleOverride } from "@/lib/types";

const PENDING_OVERRIDE: ScheduleOverride = {
  id: 7,
  override_date: "2026-01-15",
  assigned_parent: "Parent B",
  override_type: "Holiday",
  description: "Take the kids to grandma's",
  is_active: false,
  status: "Pending",
  requested_by_user_id: 101,
};

describe("PendingOverrides", () => {
  it("renders each pending request with its details", async () => {
    const fetchPendingOverrides: FetchPendingOverrides = vi.fn(async () => [
      PENDING_OVERRIDE,
    ]);

    render(
      <PendingOverrides
        fetchPendingOverrides={fetchPendingOverrides}
        decideOverride={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/2026-01-15/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Take the kids to grandma's/)).toBeInTheDocument();
    expect(screen.getByText(/Parent B/)).toBeInTheDocument();
  });

  it("shows a placeholder when there are no pending requests", async () => {
    const fetchPendingOverrides: FetchPendingOverrides = vi.fn(async () => []);

    render(
      <PendingOverrides
        fetchPendingOverrides={fetchPendingOverrides}
        decideOverride={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("No pending override requests.")).toBeInTheDocument();
    });
  });

  it("approves a request and refreshes the list", async () => {
    const user = userEvent.setup();
    const fetchPendingOverrides: FetchPendingOverrides = vi
      .fn()
      .mockResolvedValueOnce([PENDING_OVERRIDE])
      .mockResolvedValueOnce([]);
    const decideOverride = vi.fn<DecideOverride>(async () => ({
      ok: true,
      data: { ...PENDING_OVERRIDE, status: "Approved", is_active: true },
    }));

    render(
      <PendingOverrides
        fetchPendingOverrides={fetchPendingOverrides}
        decideOverride={decideOverride}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Approve" }));

    expect(decideOverride).toHaveBeenCalledWith(7, true);
    await waitFor(() => {
      expect(screen.getByText("No pending override requests.")).toBeInTheDocument();
    });
  });

  it("shows the backend's error message when a decision is rejected (e.g. self-approval)", async () => {
    const user = userEvent.setup();
    const fetchPendingOverrides: FetchPendingOverrides = vi.fn(async () => [
      PENDING_OVERRIDE,
    ]);
    const decideOverride = vi.fn<DecideOverride>(async () => ({
      ok: false,
      status: 403,
      detail: "Cannot decide on your own override request.",
    }));

    render(
      <PendingOverrides
        fetchPendingOverrides={fetchPendingOverrides}
        decideOverride={decideOverride}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(
        screen.getByText("Cannot decide on your own override request."),
      ).toBeInTheDocument();
    });
  });

  it("rejects a request via the Reject button", async () => {
    const user = userEvent.setup();
    const fetchPendingOverrides: FetchPendingOverrides = vi
      .fn()
      .mockResolvedValueOnce([PENDING_OVERRIDE])
      .mockResolvedValueOnce([]);
    const decideOverride = vi.fn<DecideOverride>(async () => ({
      ok: true,
      data: { ...PENDING_OVERRIDE, status: "Rejected" },
    }));

    render(
      <PendingOverrides
        fetchPendingOverrides={fetchPendingOverrides}
        decideOverride={decideOverride}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Reject" }));

    expect(decideOverride).toHaveBeenCalledWith(7, false);
  });
});
