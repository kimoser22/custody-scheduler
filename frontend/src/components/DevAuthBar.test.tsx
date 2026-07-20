import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DevAuthBar } from "@/components/DevAuthBar";
import type { LoginOutcome } from "@/lib/api/auth";
import { getAuthToken, getSession } from "@/lib/auth";

describe("DevAuthBar", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("logs in with a passcode and stores the returned session", async () => {
    const user = userEvent.setup();
    const loginFn = vi.fn(
      async (userId: number): Promise<LoginOutcome> => ({
        ok: true,
        status: 200,
        data: {
          access_token: "signed.token.value",
          token_type: "bearer",
          user_id: userId,
          role: "Parent",
        },
      }),
    );

    render(<DevAuthBar loginFn={loginFn} />);

    await user.selectOptions(screen.getByLabelText("Identity"), "Parent A");
    await user.type(screen.getByLabelText("Passcode"), "alpha-pass");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(getAuthToken()).toBe("signed.token.value"));
    expect(loginFn).toHaveBeenCalledWith(101, "alpha-pass");
    expect(getSession()).toEqual({
      token: "signed.token.value",
      userId: 101,
      role: "Parent",
    });
  });

  it("shows an error and stores nothing when the passcode is rejected", async () => {
    const user = userEvent.setup();
    const loginFn = vi.fn(
      async (): Promise<LoginOutcome> => ({
        ok: false,
        status: 401,
        detail: "Invalid credentials.",
      }),
    );

    render(<DevAuthBar loginFn={loginFn} />);

    await user.type(screen.getByLabelText("Passcode"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Invalid credentials.")).toBeInTheDocument();
    expect(getSession()).toBeNull();
  });
});
