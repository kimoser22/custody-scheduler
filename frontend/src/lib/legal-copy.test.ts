import { describe, expect, it } from "vitest";

import { PRIVACY_BODY, TERMS_BODY } from "@/lib/legal-copy";

describe("legal-copy (A2P campaign requirements)", () => {
  it("privacy includes Twilio pass-review non-sharing statement", () => {
    expect(PRIVACY_BODY).toContain(
      "We do not share, sell, or provide your mobile phone number or messaging consent data to third parties or affiliates for marketing or promotional purposes.",
    );
  });

  it("privacy discloses message frequency and rates", () => {
    expect(PRIVACY_BODY).toContain("Message frequency varies");
    expect(PRIVACY_BODY).toContain("approximately 10 messages per month");
    expect(PRIVACY_BODY).toContain("Message and data rates may apply");
  });

  it("privacy explains phone collection and messaging program usage", () => {
    expect(PRIVACY_BODY.toLowerCase()).toContain("mobile phone number");
    expect(PRIVACY_BODY.toLowerCase()).toMatch(
      /calendar schedule|custody swap/,
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
