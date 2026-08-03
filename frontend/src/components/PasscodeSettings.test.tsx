import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PasscodeSettings } from "@/components/PasscodeSettings";
import type { ChangePasscode } from "@/lib/api/me";

describe("PasscodeSettings", () => {
  it("submits current and new passcode on success", async () => {
    const user = userEvent.setup();
    const changePasscode = vi.fn<ChangePasscode>(async () => ({ ok: true }));

    render(<PasscodeSettings changePasscode={changePasscode} />);

    await user.type(screen.getByLabelText("Current passcode"), "old-pass");
    await user.type(screen.getByLabelText("New passcode"), "new-pass");
    await user.type(screen.getByLabelText("Confirm new passcode"), "new-pass");
    await user.click(screen.getByRole("button", { name: "Change passcode" }));

    await waitFor(() => {
      expect(changePasscode).toHaveBeenCalledWith({
        current_passcode: "old-pass",
        new_passcode: "new-pass",
      });
    });
    expect(screen.getByText("Passcode updated.")).toBeInTheDocument();
    expect(screen.getByLabelText("Current passcode")).toHaveValue("");
  });

  it("rejects mismatched confirmation without calling the API", async () => {
    const user = userEvent.setup();
    const changePasscode = vi.fn<ChangePasscode>(async () => ({ ok: true }));

    render(<PasscodeSettings changePasscode={changePasscode} />);

    await user.type(screen.getByLabelText("Current passcode"), "old-pass");
    await user.type(screen.getByLabelText("New passcode"), "new-pass");
    await user.type(screen.getByLabelText("Confirm new passcode"), "other");
    await user.click(screen.getByRole("button", { name: "Change passcode" }));

    expect(
      screen.getByText("New passcode and confirmation do not match."),
    ).toBeInTheDocument();
    expect(changePasscode).not.toHaveBeenCalled();
  });

  it("shows API error detail on failed change", async () => {
    const user = userEvent.setup();
    const changePasscode = vi.fn<ChangePasscode>(async () => ({
      ok: false,
      status: 401,
      detail: "Current passcode is incorrect.",
    }));

    render(<PasscodeSettings changePasscode={changePasscode} />);

    await user.type(screen.getByLabelText("Current passcode"), "wrong");
    await user.type(screen.getByLabelText("New passcode"), "new-pass");
    await user.type(screen.getByLabelText("Confirm new passcode"), "new-pass");
    await user.click(screen.getByRole("button", { name: "Change passcode" }));

    await waitFor(() => {
      expect(
        screen.getByText("Current passcode is incorrect."),
      ).toBeInTheDocument();
    });
  });
});
