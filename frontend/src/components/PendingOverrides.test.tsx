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
  expires_at: "2026-01-16T12:00:00",
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
        currentUserId={102}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/2026-01-15/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Take the kids to grandma's/)).toBeInTheDocument();
    expect(screen.getByText(/Parent B/)).toBeInTheDocument();
    expect(screen.getByText(/Requested by user 101/)).toBeInTheDocument();
    expect(screen.getByText(/Expires 2026-01-16T12:00:00/)).toBeInTheDocument();
  });

  it("hides Approve and Reject on your own requests", async () => {
    const fetchPendingOverrides: FetchPendingOverrides = vi.fn(async () => [
      PENDING_OVERRIDE,
    ]);

    render(
      <PendingOverrides
        fetchPendingOverrides={fetchPendingOverrides}
        decideOverride={vi.fn()}
        currentUserId={101}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/2026-01-15/)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(screen.getByText("Waiting for the other parent")).toBeInTheDocument();
  });

  it("shows Approve and Reject for requests from the other parent", async () => {
    const fetchPendingOverrides: FetchPendingOverrides = vi.fn(async () => [
      PENDING_OVERRIDE,
    ]);

    render(
      <PendingOverrides
        fetchPendingOverrides={fetchPendingOverrides}
        decideOverride={vi.fn()}
        currentUserId={102}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  it("shows a placeholder when there are no pending requests", async () => {
    const fetchPendingOverrides: FetchPendingOverrides = vi.fn(async () => []);

    render(
      <PendingOverrides
        fetchPendingOverrides={fetchPendingOverrides}
        decideOverride={vi.fn()}
        currentUserId={102}
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
        currentUserId={102}
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

  it("shows the backend's error message when a decision is rejected", async () => {
    const user = userEvent.setup();
    const fetchPendingOverrides: FetchPendingOverrides = vi.fn(async () => [
      PENDING_OVERRIDE,
    ]);
    const decideOverride = vi.fn<DecideOverride>(async () => ({
      ok: false,
      status: 409,
      detail: "Override request has already been approved.",
    }));

    render(
      <PendingOverrides
        fetchPendingOverrides={fetchPendingOverrides}
        decideOverride={decideOverride}
        currentUserId={102}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(
        screen.getByText("Override request has already been approved."),
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
        currentUserId={102}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Reject" }));

    expect(decideOverride).toHaveBeenCalledWith(7, false);
  });
});
