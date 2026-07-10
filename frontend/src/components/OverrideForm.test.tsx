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
    await user.click(screen.getByRole("button", { name: "Save override" }));

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

    await user.type(screen.getByLabelText("Description"), "Holiday");
    await user.click(screen.getByRole("button", { name: "Save override" }));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled();
    });
  });
});
