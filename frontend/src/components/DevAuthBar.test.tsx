import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { DevAuthBar } from "@/components/DevAuthBar";
import { getAuthToken } from "@/lib/auth";

describe("DevAuthBar", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("updates stored token when role changes", async () => {
    const user = userEvent.setup();
    render(<DevAuthBar />);

    await user.selectOptions(screen.getByLabelText("Role"), "Parent");
    expect(getAuthToken()).toBe("parent:dev");

    await user.selectOptions(screen.getByLabelText("Role"), "Viewer");
    expect(getAuthToken()).toBe("viewer:dev");
  });
});
