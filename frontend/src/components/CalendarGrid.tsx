import { DayCell } from "@/components/DayCell";
import type { DailyCustodyState } from "@/lib/types";

interface CalendarGridProps {
  days: DailyCustodyState[];
  monthStartDate: string;
  onDaySelect?: (day: DailyCustodyState) => void;
}

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function leadingBlankCount(monthStartDate: string): number {
  const [year, month, day] = monthStartDate.split("-").map(Number);
  return new Date(year, month - 1, day).getDay();
}

export function CalendarGrid({
  days,
  monthStartDate,
  onDaySelect,
}: CalendarGridProps) {
  const blanks = leadingBlankCount(monthStartDate);

  return (
    <div>
      <div className="mb-2 grid grid-cols-7 gap-2 text-center text-xs font-medium text-slate-500">
        {WEEKDAY_LABELS.map((label) => (
          <div key={label}>{label}</div>
        ))}
      </div>
      <div role="grid" className="grid grid-cols-7 gap-2">
        {Array.from({ length: blanks }, (_, index) => (
          <div key={`blank-${index}`} aria-hidden className="rounded border border-transparent p-2" />
        ))}
        {days.map((day) => (
          <DayCell key={day.current_date} day={day} onSelect={onDaySelect} />
        ))}
      </div>
    </div>
  );
}
