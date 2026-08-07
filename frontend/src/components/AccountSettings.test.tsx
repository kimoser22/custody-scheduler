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

  it("omits Contact settings when showContacts is false", async () => {
    const user = userEvent.setup();
    render(
      <AccountSettings showContacts={false}>
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

  it("shows Contact settings when showContacts is true", async () => {
    const user = userEvent.setup();
    render(
      <AccountSettings showContacts>
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
