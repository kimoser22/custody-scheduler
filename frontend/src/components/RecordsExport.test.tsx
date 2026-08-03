import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RecordsExport } from "@/components/RecordsExport";
import type { DownloadFamilyExport } from "@/lib/api/export";

describe("RecordsExport", () => {
  it("downloads records when signed in", async () => {
    const user = userEvent.setup();
    const downloadFamilyExport = vi.fn<DownloadFamilyExport>(async () => ({
      ok: true,
      filename: "custody-export-2026-08-03.json",
    }));

    render(<RecordsExport downloadFamilyExport={downloadFamilyExport} />);

    await user.click(screen.getByRole("button", { name: "Download records" }));

    await waitFor(() => {
      expect(
        screen.getByText("Downloaded custody-export-2026-08-03.json."),
      ).toBeInTheDocument();
    });
    expect(downloadFamilyExport).toHaveBeenCalledTimes(1);
  });

  it("shows API errors", async () => {
    const user = userEvent.setup();
    const downloadFamilyExport = vi.fn<DownloadFamilyExport>(async () => ({
      ok: false,
      status: 401,
      detail: "Not authenticated",
    }));

    render(<RecordsExport downloadFamilyExport={downloadFamilyExport} />);
    await user.click(screen.getByRole("button", { name: "Download records" }));

    await waitFor(() => {
      expect(screen.getByText("Not authenticated")).toBeInTheDocument();
    });
  });
});
