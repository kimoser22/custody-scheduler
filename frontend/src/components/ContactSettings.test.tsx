import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ContactSettings } from "@/components/ContactSettings";
import type { FetchMe, UpdateMe } from "@/lib/api/me";

describe("ContactSettings", () => {
  it("loads and saves phone and email", async () => {
    const user = userEvent.setup();
    const fetchMe = vi.fn<FetchMe>(async () => ({
      id: 101,
      role: "Parent",
      custody_label: "Parent A",
      phone: "+15550001",
      email: "a@example.com",
    }));
    const updateMe = vi.fn<UpdateMe>(async (update) => ({
      ok: true,
      data: {
        id: 101,
        role: "Parent",
        custody_label: "Parent A",
        phone: update.phone ?? null,
        email: update.email ?? null,
      },
    }));

    render(<ContactSettings fetchMe={fetchMe} updateMe={updateMe} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Phone")).toHaveValue("+15550001");
    });
    expect(screen.getByLabelText("Email")).toHaveValue("a@example.com");

    await user.clear(screen.getByLabelText("Phone"));
    await user.type(screen.getByLabelText("Phone"), "+15559999");
    await user.clear(screen.getByLabelText("Email"));
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.click(screen.getByRole("button", { name: "Save contacts" }));

    await waitFor(() => {
      expect(updateMe).toHaveBeenCalledWith({
        phone: "+15559999",
        email: "new@example.com",
      });
    });
    expect(screen.getByText("Contact settings saved.")).toBeInTheDocument();
  });

  it("shows API error detail on failed save", async () => {
    const user = userEvent.setup();
    const fetchMe = vi.fn<FetchMe>(async () => ({
      id: 101,
      role: "Parent",
      custody_label: "Parent A",
      phone: "+15550001",
      email: null,
    }));
    const updateMe = vi.fn<UpdateMe>(async () => ({
      ok: false,
      status: 409,
      detail: "phone is already in use.",
    }));

    render(<ContactSettings fetchMe={fetchMe} updateMe={updateMe} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Phone")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Save contacts" }));

    await waitFor(() => {
      expect(screen.getByText("phone is already in use.")).toBeInTheDocument();
    });
  });
});
