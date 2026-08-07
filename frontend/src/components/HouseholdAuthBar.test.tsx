import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HouseholdAuthBar } from "@/components/HouseholdAuthBar";
import type { LoginOutcome } from "@/lib/api/auth";
import { getAuthToken, getSession, login } from "@/lib/auth";

describe("HouseholdAuthBar", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("restores an existing session from localStorage on mount instead of showing signed-out", async () => {
    const loginFn = vi.fn(
      async (): Promise<LoginOutcome> => ({
        ok: true,
        status: 200,
        data: {
          access_token: "restored.token.value",
          token_type: "bearer",
          user_id: 102,
          role: "Parent",
        },
      }),
    );
    await login(102, "bravo-pass", loginFn);

    const onAuthChange = vi.fn();
    render(<HouseholdAuthBar onAuthChange={onAuthChange} />);

    expect(await screen.findByText(/Signed in as Parent B/)).toBeInTheDocument();
    expect(screen.queryByText("Not signed in")).not.toBeInTheDocument();
    expect(screen.queryByText(/\(user /)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Passcode")).not.toBeInTheDocument();
  });

  it("shows not-signed-in on mount when localStorage has no session", () => {
    render(<HouseholdAuthBar />);
    expect(screen.getByText("Not signed in")).toBeInTheDocument();
    expect(screen.getByLabelText("Household member")).toBeInTheDocument();
    expect(screen.getByLabelText("Passcode")).toBeInTheDocument();
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

    render(<HouseholdAuthBar loginFn={loginFn} />);

    await user.selectOptions(screen.getByLabelText("Household member"), "Parent A");
    await user.type(screen.getByLabelText("Passcode"), "alpha-pass");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(getAuthToken()).toBe("signed.token.value"));
    expect(loginFn).toHaveBeenCalledWith(101, "alpha-pass");
    expect(getSession()).toEqual({
      token: "signed.token.value",
      userId: 101,
      role: "Parent",
    });
    expect(await screen.findByText(/Signed in as Parent A/)).toBeInTheDocument();
    expect(screen.queryByText(/\(user /)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Passcode")).not.toBeInTheDocument();
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

    render(<HouseholdAuthBar loginFn={loginFn} />);

    await user.type(screen.getByLabelText("Passcode"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Invalid credentials.")).toBeInTheDocument();
    expect(getSession()).toBeNull();
  });
});
