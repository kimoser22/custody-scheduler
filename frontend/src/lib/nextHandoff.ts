import type { DailyCustodyState, ParentRole } from "@/lib/types";

/**
 * Look-ahead for the sticky next-handoff cue — twin of HANDOFF_HORIZON_DAYS in
 * core/schedule_summary.py. Baseline handoffs land every 2–3 days; 45 exists so
 * an approved holiday block that blankets weeks still surfaces the next flip.
 */
export const HANDOFF_HORIZON_DAYS = 45;

export type ParentLabel = "Parent A" | "Parent B";

export interface NextHandoff {
  date: string;
  parent: ParentRole;
}

function dayBefore(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const prev = new Date(y, m - 1, d - 1);
  const year = prev.getFullYear();
  const month = String(prev.getMonth() + 1).padStart(2, "0");
  const day = String(prev.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function isContiguous(sorted: DailyCustodyState[]): boolean {
  for (let i = 1; i < sorted.length; i += 1) {
    if (dayBefore(sorted[i].current_date) !== sorted[i - 1].current_date) {
      return false;
    }
  }
  return true;
}

/** First day after `fromDate` where `final_parent` flips; null if unknown. */
export function findNextHandoff(
  days: DailyCustodyState[],
  fromDate: string,
): NextHandoff | null {
  if (days.length === 0) {
    return null;
  }
  const sorted = [...days].sort((a, b) =>
    a.current_date < b.current_date ? -1 : a.current_date > b.current_date ? 1 : 0,
  );
  if (!isContiguous(sorted)) {
    return null;
  }
  const today = sorted.find((day) => day.current_date === fromDate);
  if (!today) {
    return null;
  }
  const todayParent = today.final_parent;
  for (const day of sorted) {
    if (day.current_date > fromDate && day.final_parent !== todayParent) {
      return { date: day.current_date, parent: day.final_parent };
    }
  }
  return null;
}

export function formatHandoffCue({
  handoff,
  myLabel,
}: {
  handoff: NextHandoff;
  myLabel: ParentLabel | null;
}): string {
  if (myLabel == null) {
    return `Next: ${handoff.parent} on ${handoff.date}`;
  }
  if (handoff.parent === myLabel) {
    return `Back to you: ${handoff.date}`;
  }
  return `${handoff.parent} has them ${handoff.date}`;
}
