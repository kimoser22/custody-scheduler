import { describe, expect, it } from "vitest";

import { findNextHandoff, formatHandoffCue } from "@/lib/nextHandoff";
import type { DailyCustodyState, ParentRole } from "@/lib/types";

function days(
  start: string,
  parents: ParentRole[],
): DailyCustodyState[] {
  const [y, m, d] = start.split("-").map(Number);
  return parents.map((parent, offset) => {
    const date = new Date(y, m - 1, d + offset);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return {
      current_date: `${year}-${month}-${day}`,
      baseline_parent: parent,
      final_parent: parent,
      is_overridden: false,
    };
  });
}

describe("findNextHandoff", () => {
  it("finds the flip after a same-parent streak", () => {
    expect(findNextHandoff(days("2026-08-15", ["Parent A", "Parent A", "Parent A", "Parent B"]), "2026-08-15")).toEqual({
      date: "2026-08-18",
      parent: "Parent B",
    });
  });

  it("finds a handoff tomorrow", () => {
    expect(findNextHandoff(days("2026-08-15", ["Parent A", "Parent B"]), "2026-08-15")).toEqual({
      date: "2026-08-16",
      parent: "Parent B",
    });
  });

  it("returns null when there is no flip in the window", () => {
    expect(findNextHandoff(days("2026-08-15", ["Parent A", "Parent A", "Parent A"]), "2026-08-15")).toBeNull();
  });

  it("accepts unsorted input", () => {
    const unsorted = days("2026-08-15", ["Parent A", "Parent B"]).reverse();
    expect(findNextHandoff(unsorted, "2026-08-15")).toEqual({
      date: "2026-08-16",
      parent: "Parent B",
    });
  });

  it("returns null when today is missing from the list", () => {
    expect(findNextHandoff(days("2026-08-16", ["Parent A", "Parent B"]), "2026-08-15")).toBeNull();
  });

  it("returns null when the day list has a gap", () => {
    const withGap = [
      ...days("2026-08-15", ["Parent A"]),
      ...days("2026-08-17", ["Parent B"]),
    ];
    expect(findNextHandoff(withGap, "2026-08-15")).toBeNull();
  });
});

describe("formatHandoffCue", () => {
  const handoff = { date: "2026-08-12", parent: "Parent A" as const };

  it("orients as Back to you when the next run is yours", () => {
    expect(formatHandoffCue({ handoff, myLabel: "Parent A" })).toBe(
      "Back to you: 2026-08-12",
    );
  });

  it("orients as other has them when you hold them now", () => {
    expect(
      formatHandoffCue({
        handoff: { date: "2026-08-12", parent: "Parent B" },
        myLabel: "Parent A",
      }),
    ).toBe("Parent B has them 2026-08-12");
  });

  it("uses neutral Next copy for Viewer / unknown", () => {
    expect(formatHandoffCue({ handoff, myLabel: null })).toBe(
      "Next: Parent A on 2026-08-12",
    );
  });
});
