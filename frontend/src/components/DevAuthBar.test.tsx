import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { DevAuthBar } from "@/components/DevAuthBar";
import { getAuthToken } from "@/lib/auth";

describe("DevAuthBar", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("updates stored token when identity changes", async () => {
    const user = userEvent.setup();
    render(<DevAuthBar />);

    await user.selectOptions(screen.getByLabelText("Identity"), "Parent A");
    expect(getAuthToken()).toBe("parent:a");

    await user.selectOptions(screen.getByLabelText("Identity"), "Parent B");
    expect(getAuthToken()).toBe("parent:b");

    await user.selectOptions(screen.getByLabelText("Identity"), "Viewer");
    expect(getAuthToken()).toBe("viewer:dev");
  });
});
