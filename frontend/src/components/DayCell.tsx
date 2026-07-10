import type { DailyCustodyState } from "@/lib/types";
import { PARENT_A } from "@/lib/types";

interface DayCellProps {
  day: DailyCustodyState;
  onSelect?: (day: DailyCustodyState) => void;
}

export function DayCell({ day, onSelect }: DayCellProps) {
  const parentClass =
    day.final_parent === PARENT_A ? "parent-a" : "parent-b";

  return (
    <button
      type="button"
      role="gridcell"
      data-overridden={day.is_overridden ? "true" : "false"}
      data-parent={parentClass}
      title={day.override_details?.description}
      className={`rounded border p-2 text-left text-sm ${parentClass} ${
        day.is_overridden ? "ring-2 ring-amber-500" : ""
      }`}
      onClick={() => onSelect?.(day)}
    >
      <div className="font-medium">{day.current_date.slice(8)}</div>
      <div>{day.final_parent}</div>
      {day.is_overridden ? (
        <span className="mt-1 inline-block text-xs text-amber-700">Override</span>
      ) : null}
    </button>
  );
}
