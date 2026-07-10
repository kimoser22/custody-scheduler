export type ParentRole = "Parent A" | "Parent B";
export type OverrideType = "Holiday" | "Mutual Swap" | "Emergency";

export interface ScheduleOverride {
  override_date: string;
  assigned_parent: ParentRole;
  override_type: OverrideType;
  description: string;
  is_active: boolean;
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
