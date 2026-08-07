import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PendingOverrides } from "@/components/PendingOverrides";
import type {
  DecideOverride,
  FetchPendingOverrides,
  SweepExpiredOverrides,
} from "@/lib/api/schedule";
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
  requested_by_label: "Parent A",
  expires_at: "2026-01-16T12:00:00",
};

describe("PendingOverrides", () => {
  it("renders each pending request with title-first hierarchy", async () => {
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
      expect(
        screen.getByText("Holiday / vacation · Parent B"),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("2026-01-15")).toBeInTheDocument();
    expect(screen.queryByText(/2026-01-15 to/)).not.toBeInTheDocument();
    expect(screen.getByText(/Take the kids to grandma's/)).toBeInTheDocument();
    expect(screen.getByText(/Requested by Parent A/)).toBeInTheDocument();
    expect(screen.getByText(/UTC/)).toBeInTheDocument();
  });

  it("renders multi-day ranges with duration on a separate date line", async () => {
    const fetchPendingOverrides: FetchPendingOverrides = vi.fn(async () => [
      {
        ...PENDING_OVERRIDE,
        id: 8,
        override_date: "2026-01-10",
        end_date: "2026-01-14",
        description: "Winter trip",
      },
    ]);

    render(
      <PendingOverrides
        fetchPendingOverrides={fetchPendingOverrides}
        decideOverride={vi.fn()}
        currentUserId={102}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByText("Holiday / vacation · Parent B"),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("2026-01-10 to 2026-01-14")).toBeInTheDocument();
    expect(screen.getByText(/5 days/)).toBeInTheDocument();
    expect(screen.getByText("Winter trip")).toBeInTheDocument();
  });

  it("calls sweep-expired before loading pending requests", async () => {
    const sweepExpiredOverrides = vi.fn<SweepExpiredOverrides>(async () => undefined);
    const fetchPendingOverrides: FetchPendingOverrides = vi.fn(async () => []);

    render(
      <PendingOverrides
        fetchPendingOverrides={fetchPendingOverrides}
        decideOverride={vi.fn()}
        sweepExpiredOverrides={sweepExpiredOverrides}
        currentUserId={102}
      />,
    );

    await waitFor(() => {
      expect(sweepExpiredOverrides).toHaveBeenCalled();
    });
    expect(fetchPendingOverrides).toHaveBeenCalled();
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
      expect(
        screen.getByText(/No pending requests\. Expired ones drop off/),
      ).toBeInTheDocument();
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
      expect(
        screen.getByText(/No pending requests\. Expired ones drop off/),
      ).toBeInTheDocument();
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

  it("removes the row and shows a notice when the request has expired", async () => {
    const user = userEvent.setup();
    const fetchPendingOverrides: FetchPendingOverrides = vi
      .fn()
      .mockResolvedValueOnce([PENDING_OVERRIDE])
      .mockResolvedValueOnce([]);
    const decideOverride = vi.fn<DecideOverride>(async () => ({
      ok: false,
      status: 410,
      detail: "Override request has expired.",
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
      expect(screen.getByText("This request expired.")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
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
