import { DayCell } from "@/components/DayCell";
import type { DailyCustodyState } from "@/lib/types";

interface CalendarGridProps {
  days: DailyCustodyState[];
  monthStartDate: string;
  onDaySelect?: (day: DailyCustodyState) => void;
}

const WEEKDAY_LABELS = [
  { short: "S", full: "Sun" },
  { short: "M", full: "Mon" },
  { short: "T", full: "Tue" },
  { short: "W", full: "Wed" },
  { short: "T", full: "Thu" },
  { short: "F", full: "Fri" },
  { short: "S", full: "Sat" },
] as const;

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
      <div className="mb-2 grid grid-cols-7 gap-1 text-center text-xs font-medium text-slate-500 sm:gap-2">
        {WEEKDAY_LABELS.map(({ short, full }) => (
          <div key={full}>
            <span className="sm:hidden">{short}</span>
            <span className="hidden sm:inline">{full}</span>
          </div>
        ))}
      </div>
      <div role="grid" className="grid grid-cols-7 gap-1 sm:gap-2">
        {Array.from({ length: blanks }, (_, index) => (
          <div
            key={`blank-${index}`}
            aria-hidden
            className="rounded border border-transparent p-1 sm:p-2"
          />
        ))}
        {days.map((day) => (
          <DayCell key={day.current_date} day={day} onSelect={onDaySelect} />
        ))}
      </div>
    </div>
  );
}
