import type { DailyCustodyState } from "@/lib/types";
import { PARENT_A } from "@/lib/types";
import { dayOfMonthLabel, shortParentLabel } from "@/lib/formatOverrideDisplay";

interface DayCellProps {
  day: DailyCustodyState;
  onSelect?: (day: DailyCustodyState) => void;
}

/** Short badge for overridden days: prefer description, else type label. */
export function overrideBadgeLabel(day: DailyCustodyState): string {
  const details = day.override_details;
  if (!details) {
    return "Override";
  }
  const desc = details.description?.trim();
  if (desc) {
    return desc.length > 18 ? `${desc.slice(0, 16)}…` : desc;
  }
  if (details.override_type === "Holiday") {
    return "Holiday";
  }
  return details.override_type;
}

export function DayCell({ day, onSelect }: DayCellProps) {
  const parentClass =
    day.final_parent === PARENT_A ? "parent-a" : "parent-b";
  const badge = day.is_overridden ? overrideBadgeLabel(day) : null;
  const dayNumber = dayOfMonthLabel(day.current_date);
  const shortParent = shortParentLabel(day.final_parent);
  const ariaLabel = `${day.current_date}, ${day.final_parent}`;

  return (
    <button
      type="button"
      role="gridcell"
      aria-label={ariaLabel}
      data-overridden={day.is_overridden ? "true" : "false"}
      data-parent={parentClass}
      title={day.override_details?.description || day.override_details?.override_type}
      className={`rounded border p-1 text-left text-xs sm:p-2 sm:text-sm ${parentClass} ${
        day.is_overridden ? "ring-2 ring-amber-500" : ""
      }`}
      onClick={() => onSelect?.(day)}
    >
      <div className="font-medium" aria-hidden="true">
        {dayNumber}
      </div>
      <div aria-hidden="true">{shortParent}</div>
      {badge ? (
        <span className="mt-1 inline-block line-clamp-1 text-xs text-amber-700">
          {badge}
        </span>
      ) : null}
    </button>
  );
}
