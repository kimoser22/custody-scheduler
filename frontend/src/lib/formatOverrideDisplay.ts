import type { OverrideType, ParentRole } from "@/lib/types";
import { PARENT_A } from "@/lib/types";

/** Unpadded day-of-month from an ISO `YYYY-MM-DD` date. */
export function dayOfMonthLabel(isoDate: string): string {
  const day = Number(isoDate.slice(8, 10));
  return Number.isFinite(day) ? String(day) : isoDate.slice(8);
}

/** Compact parent code for calendar cells. */
export function shortParentLabel(parent: ParentRole): string {
  return parent === PARENT_A ? "A" : "B";
}

/** Pending-card type label (Holiday gets vacation wording). */
export function overrideTypeLabel(overrideType: OverrideType): string {
  if (overrideType === "Holiday") {
    return "Holiday / vacation";
  }
  return overrideType;
}

export interface OverrideRangeDisplay {
  dateLine: string;
  /** Inclusive day count when multi-day; null for single-day. */
  dayCount: number | null;
}

/** Format override start/end for pending cards. */
export function formatOverrideRange(
  overrideDate: string,
  endDate?: string | null,
): OverrideRangeDisplay {
  if (!endDate || endDate === overrideDate) {
    return { dateLine: overrideDate, dayCount: null };
  }

  const start = Date.parse(`${overrideDate}T00:00:00Z`);
  const end = Date.parse(`${endDate}T00:00:00Z`);
  const dayCount =
    Number.isFinite(start) && Number.isFinite(end)
      ? Math.floor((end - start) / (24 * 60 * 60 * 1000)) + 1
      : null;

  return {
    dateLine: `${overrideDate} to ${endDate}`,
    dayCount: dayCount != null && dayCount > 0 ? dayCount : null,
  };
}
