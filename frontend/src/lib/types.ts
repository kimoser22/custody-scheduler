export type ParentRole = "Parent A" | "Parent B";
export type OverrideType = "Holiday" | "Mutual Swap" | "Emergency";
export type OverrideStatus = "Draft" | "Pending" | "Approved" | "Rejected" | "Expired";

export interface ScheduleOverride {
  id?: number | null;
  override_date: string;
  /** Inclusive end; omit or null means single-day (same as override_date). */
  end_date?: string | null;
  assigned_parent: ParentRole;
  override_type: OverrideType;
  description: string;
  is_active: boolean;
  status: OverrideStatus;
  expires_at?: string | null;
  requested_by_user_id?: number | null;
}

export interface DailyCustodyState {
  current_date: string;
  baseline_parent: ParentRole;
  final_parent: ParentRole;
  is_overridden: boolean;
  override_details?: ScheduleOverride | null;
}

export const PARENT_A: ParentRole = "Parent A";
export const PARENT_B: ParentRole = "Parent B";
