import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TermsBody } from "@/components/TermsBody";

describe("TermsBody", () => {
  it("renders STOP and HELP inside strong elements", () => {
    render(
      <TermsBody
        body={`Reply STOP to opt out of messaging. Reply HELP for help.`}
      />,
    );

    const stop = screen.getByText("STOP");
    const help = screen.getByText("HELP");
    expect(stop.tagName).toBe("STRONG");
    expect(help.tagName).toBe("STRONG");
  });
});
