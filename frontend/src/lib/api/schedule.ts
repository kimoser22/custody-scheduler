import type { DailyCustodyState, ScheduleOverride } from "@/lib/types";

export interface ScheduleQuery {
  start_date: string;
  end_date: string;
}

export type FetchSchedule = (
  query: ScheduleQuery,
) => Promise<DailyCustodyState[]>;

export type CreateOverride = (
  override: ScheduleOverride,
) => Promise<{ ok: true; data: ScheduleOverride } | { ok: false; status: number; detail?: string }>;
