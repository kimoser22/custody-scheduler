import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  AccountSettings,
  AccountSettingsSection,
} from "@/components/AccountSettings";

describe("AccountSettings", () => {
  it("is collapsed by default and hides section bodies", () => {
    render(
      <AccountSettings>
        <AccountSettingsSection id="passcode" title="Passcode">
          <p>Passcode body</p>
        </AccountSettingsSection>
        <AccountSettingsSection id="calendar" title="Calendar subscribe">
          <p>Calendar body</p>
        </AccountSettingsSection>
      </AccountSettings>,
    );

    const toggle = screen.getByRole("button", { name: "Account & settings" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Passcode body")).not.toBeInTheDocument();
    expect(screen.queryByText("Calendar body")).not.toBeInTheDocument();
  });

  it("expands to show section titles and children", async () => {
    const user = userEvent.setup();
    render(
      <AccountSettings>
        <AccountSettingsSection id="passcode" title="Passcode">
          <p>Passcode body</p>
        </AccountSettingsSection>
        <AccountSettingsSection id="download" title="Download records">
          <p>Download body</p>
        </AccountSettingsSection>
      </AccountSettings>,
    );

    await user.click(screen.getByRole("button", { name: "Account & settings" }));

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Account & settings" }),
      ).toHaveAttribute("aria-expanded", "true");
    });
    expect(screen.getByText("Passcode")).toBeInTheDocument();
    expect(screen.getByText("Passcode body")).toBeInTheDocument();
    expect(screen.getByText("Download records")).toBeInTheDocument();
    expect(screen.getByText("Download body")).toBeInTheDocument();
  });

  it("omits Contact settings when isParent is false", async () => {
    const user = userEvent.setup();
    render(
      <AccountSettings isParent={false}>
        <AccountSettingsSection id="passcode" title="Passcode">
          <p>Passcode body</p>
        </AccountSettingsSection>
        <AccountSettingsSection id="contacts" title="Contact settings" parentOnly>
          <p>Contacts body</p>
        </AccountSettingsSection>
      </AccountSettings>,
    );

    await user.click(screen.getByRole("button", { name: "Account & settings" }));

    await waitFor(() => {
      expect(screen.getByText("Passcode body")).toBeInTheDocument();
    });
    expect(screen.queryByText("Contact settings")).not.toBeInTheDocument();
    expect(screen.queryByText("Contacts body")).not.toBeInTheDocument();
  });

  it("shows Contact settings when isParent is true", async () => {
    const user = userEvent.setup();
    render(
      <AccountSettings isParent>
        <AccountSettingsSection id="contacts" title="Contact settings" parentOnly>
          <p>Contacts body</p>
        </AccountSettingsSection>
      </AccountSettings>,
    );

    await user.click(screen.getByRole("button", { name: "Account & settings" }));

    await waitFor(() => {
      expect(screen.getByText("Contact settings")).toBeInTheDocument();
    });
    expect(screen.getByText("Contacts body")).toBeInTheDocument();
  });

  it("associates the toggle with the expanded region", async () => {
    const user = userEvent.setup();
    render(
      <AccountSettings>
        <AccountSettingsSection id="passcode" title="Passcode">
          <p>Passcode body</p>
        </AccountSettingsSection>
      </AccountSettings>,
    );

    const toggle = screen.getByRole("button", { name: "Account & settings" });
    const controlsId = toggle.getAttribute("aria-controls");
    expect(controlsId).toBeTruthy();

    await user.click(toggle);

    await waitFor(() => {
      expect(document.getElementById(controlsId!)).toBeInTheDocument();
    });
    expect(document.getElementById(controlsId!)).toHaveAttribute(
      "id",
      controlsId!,
    );
  });
});

describe("AccountSettings viewer gating", () => {
  // Viewer is ONE shared account. Passcode and record download are marked
  // parentOnly on the schedule page because a capability given to "the Viewer"
  // is given to every holder of that shared passcode at once: one of them could
  // rotate the passcode and lock out the rest, or download both parents'
  // contact details and the full audit log. The server refuses these regardless
  // (tests/test_viewer_role.py) — this keeps the UI from offering a button that
  // can only 403.
  function renderPanels(isParent: boolean) {
    return render(
      <AccountSettings isParent={isParent}>
        <AccountSettingsSection id="calendar" title="Calendar subscribe">
          <p>Calendar body</p>
        </AccountSettingsSection>
        <AccountSettingsSection id="passcode" title="Passcode" parentOnly>
          <p>Passcode body</p>
        </AccountSettingsSection>
        <AccountSettingsSection id="download" title="Download records" parentOnly>
          <p>Download body</p>
        </AccountSettingsSection>
      </AccountSettings>,
    );
  }

  it("hides passcode and record download from a Viewer", async () => {
    const user = userEvent.setup();
    renderPanels(false);

    await user.click(screen.getByRole("button", { name: "Account & settings" }));

    expect(screen.queryByText("Passcode body")).not.toBeInTheDocument();
    expect(screen.queryByText("Download body")).not.toBeInTheDocument();
    // Calendar subscribe is the whole reason the Viewer account exists.
    expect(screen.getByText("Calendar body")).toBeInTheDocument();
  });

  it("shows passcode and record download to a Parent", async () => {
    const user = userEvent.setup();
    renderPanels(true);

    await user.click(screen.getByRole("button", { name: "Account & settings" }));

    expect(screen.getByText("Passcode body")).toBeInTheDocument();
    expect(screen.getByText("Download body")).toBeInTheDocument();
    expect(screen.getByText("Calendar body")).toBeInTheDocument();
  });
});
