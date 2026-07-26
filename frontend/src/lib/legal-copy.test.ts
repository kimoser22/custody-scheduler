import { describe, expect, it } from "vitest";

import { PRIVACY_BODY, TERMS_BODY } from "@/lib/legal-copy";

describe("legal-copy (A2P campaign requirements)", () => {
  it("privacy states mobile info is not shared with third parties for marketing", () => {
    expect(PRIVACY_BODY).toContain(
      "No mobile information will be shared with third parties or affiliates for marketing or promotional purposes.",
    );
    expect(PRIVACY_BODY).toContain(
      "All other categories exclude text messaging originator opt-in data and consent; this information will not be shared with any third parties.",
    );
  });

  it("terms describe private non-commercial household scheduling", () => {
    const lower = TERMS_BODY.toLowerCase();
    expect(lower).toContain("private");
    expect(lower).toContain("non-commercial");
    expect(lower).toMatch(/household scheduling|custody scheduling/);
  });

  it("terms include carrier-required messaging disclosures", () => {
    expect(TERMS_BODY).toContain("Message frequency varies");
    expect(TERMS_BODY).toContain("Message and data rates may apply");
    expect(TERMS_BODY).toContain("Reply STOP to opt out");
    expect(TERMS_BODY).toContain("Reply HELP for help");
  });
});
