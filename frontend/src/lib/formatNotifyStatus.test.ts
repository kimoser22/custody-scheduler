import { describe, expect, it } from "vitest";

import {
  formatNotifyCreateNotice,
  formatNotifyStatus,
} from "@/lib/formatNotifyStatus";

describe("formatNotifyStatus", () => {
  it("omits a line while both channels are still queued", () => {
    expect(formatNotifyStatus("queued", "queued")).toBeNull();
    expect(formatNotifyStatus(null, null)).toBeNull();
  });

  it("summarizes successful dual delivery", () => {
    expect(formatNotifyStatus("sent", "sent")).toBe(
      "Notified by email and SMS",
    );
  });

  it("explains SMS opt-out with email fallback", () => {
    expect(formatNotifyStatus("sent", "skipped_opt_out")).toBe(
      "Emailed · SMS skipped (opted out)",
    );
  });

  it("explains total miss when no channels remain", () => {
    expect(formatNotifyStatus("skipped_no_address", "skipped_no_phone")).toBe(
      "Couldn't notify — no email or phone on file",
    );
    expect(formatNotifyStatus("skipped_no_address", "skipped_opt_out")).toBe(
      "Couldn't notify — other parent opted out of SMS and has no email",
    );
  });

  it("surfaces failed delivery quietly", () => {
    expect(formatNotifyStatus("failed", "sent")).toBe(
      "SMS sent · email may not have arrived",
    );
  });
});

describe("formatNotifyCreateNotice", () => {
  it("warns when SMS is opted out but email still goes", () => {
    expect(formatNotifyCreateNotice("queued", "skipped_opt_out")).toBe(
      "The other parent opted out of SMS; we emailed them instead.",
    );
  });

  it("warns when nothing can be delivered", () => {
    expect(
      formatNotifyCreateNotice("skipped_no_address", "skipped_no_phone"),
    ).toBe(
      "They won't get an automatic ping—tell them in person or update contacts.",
    );
  });

  it("stays quiet on a normal queue", () => {
    expect(formatNotifyCreateNotice("queued", "queued")).toBeNull();
  });
});
