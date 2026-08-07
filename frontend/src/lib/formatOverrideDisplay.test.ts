import { describe, expect, it } from "vitest";

import {
  dayOfMonthLabel,
  formatOverrideRange,
  overrideTypeLabel,
  shortParentLabel,
} from "@/lib/formatOverrideDisplay";
import { PARENT_A, PARENT_B } from "@/lib/types";

describe("dayOfMonthLabel", () => {
  it("returns an unpadded day number from an ISO date", () => {
    expect(dayOfMonthLabel("2026-01-05")).toBe("5");
    expect(dayOfMonthLabel("2026-01-15")).toBe("15");
  });
});

describe("shortParentLabel", () => {
  it("maps Parent A/B to A/B", () => {
    expect(shortParentLabel(PARENT_A)).toBe("A");
    expect(shortParentLabel(PARENT_B)).toBe("B");
  });
});

describe("overrideTypeLabel", () => {
  it("maps Holiday to Holiday / vacation", () => {
    expect(overrideTypeLabel("Holiday")).toBe("Holiday / vacation");
  });

  it("leaves other types unchanged", () => {
    expect(overrideTypeLabel("Mutual Swap")).toBe("Mutual Swap");
    expect(overrideTypeLabel("Emergency")).toBe("Emergency");
  });
});

describe("formatOverrideRange", () => {
  it("returns a single date when end is missing or equal", () => {
    expect(formatOverrideRange("2026-01-15")).toEqual({
      dateLine: "2026-01-15",
      dayCount: null,
    });
    expect(formatOverrideRange("2026-01-15", "2026-01-15")).toEqual({
      dateLine: "2026-01-15",
      dayCount: null,
    });
    expect(formatOverrideRange("2026-01-15", null)).toEqual({
      dateLine: "2026-01-15",
      dayCount: null,
    });
  });

  it("returns a range line and inclusive day count for multi-day", () => {
    expect(formatOverrideRange("2026-01-10", "2026-01-14")).toEqual({
      dateLine: "2026-01-10 to 2026-01-14",
      dayCount: 5,
    });
  });
});
