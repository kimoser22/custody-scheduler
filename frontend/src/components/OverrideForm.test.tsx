import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { OverrideForm } from "@/components/OverrideForm";
import type { CreateOverride } from "@/lib/api/schedule";

describe("OverrideForm", () => {
  it("shows the parent-only error message on 403", async () => {
    const user = userEvent.setup();
    const createOverride = vi.fn<CreateOverride>(async () => ({
      ok: false,
      status: 403,
      detail: "Action restricted to Parent roles only.",
    }));

    render(
      <OverrideForm
        initialDate="2026-01-15"
        createOverride={createOverride}
      />,
    );

    await user.type(screen.getByLabelText("Description"), "Holiday");
    await user.click(screen.getByRole("button", { name: "Request holiday block" }));

    await waitFor(() => {
      expect(
        screen.getByText("Action restricted to Parent roles only."),
      ).toBeInTheDocument();
    });
  });

  it("calls onSuccess after a successful save", async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    const createOverride = vi.fn<CreateOverride>(async (override) => ({
      ok: true,
      data: override,
    }));

    render(
      <OverrideForm
        initialDate="2026-01-15"
        createOverride={createOverride}
        onSuccess={onSuccess}
      />,
    );

    expect(
      screen.getByText(/Request holiday \/ vacation block for 2026-01-15/),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Description"), "Holiday");
    await user.click(screen.getByRole("button", { name: "Request holiday block" }));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled();
    });
  });

  it("shows a soft notice when the other parent opted out of SMS", async () => {
    const user = userEvent.setup();
    const createOverride = vi.fn<CreateOverride>(async (override) => ({
      ok: true,
      data: {
        ...override,
        email_notify_status: "queued",
        sms_notify_status: "skipped_opt_out",
      },
    }));

    render(
      <OverrideForm
        initialDate="2026-01-15"
        createOverride={createOverride}
      />,
    );

    await user.type(screen.getByLabelText("Description"), "Holiday");
    await user.click(screen.getByRole("button", { name: "Request holiday block" }));

    await waitFor(() => {
      expect(
        screen.getByText(
          "The other parent opted out of SMS; we emailed them instead.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("posts end_date with the selected range", async () => {
    const user = userEvent.setup();
    const createOverride = vi.fn<CreateOverride>(async (override) => ({
      ok: true,
      data: override,
    }));

    render(
      <OverrideForm
        initialDate="2026-01-15"
        createOverride={createOverride}
      />,
    );

    await user.clear(screen.getByLabelText("End date"));
    await user.type(screen.getByLabelText("End date"), "2026-01-17");
    await user.type(screen.getByLabelText("Description"), "Long weekend");
    await user.click(screen.getByRole("button", { name: "Request holiday block" }));

    await waitFor(() => {
      expect(createOverride).toHaveBeenCalledWith(
        expect.objectContaining({
          override_date: "2026-01-15",
          end_date: "2026-01-17",
          description: "Long weekend",
        }),
      );
    });
  });
});
