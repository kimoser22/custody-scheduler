"use client";

import { useMemo, useState } from "react";

import { CalendarGrid } from "@/components/CalendarGrid";
import { DevAuthBar } from "@/components/DevAuthBar";
import { OverrideForm } from "@/components/OverrideForm";
import { useSchedule } from "@/hooks/useSchedule";
import { createOverrideRequest } from "@/lib/api/overrides";
import { getAuthToken } from "@/lib/auth";
import type { DailyCustodyState } from "@/lib/types";

function formatLocalDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getMonthRange(reference = new Date()) {
  const start = new Date(reference.getFullYear(), reference.getMonth(), 1);
  const end = new Date(reference.getFullYear(), reference.getMonth() + 1, 0);
  return {
    startDate: formatLocalDate(start),
    endDate: formatLocalDate(end),
  };
}

export default function SchedulePage() {
  const { startDate, endDate } = useMemo(() => getMonthRange(), []);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const { days, isLoading, error, refetch } = useSchedule({
    startDate,
    endDate,
    authToken,
  });
  const [selectedDay, setSelectedDay] = useState<DailyCustodyState | null>(null);

  function handleAuthChange() {
    setAuthToken(getAuthToken());
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="mb-2 text-2xl font-bold">Custody Schedule</h1>
      <p className="mb-4 text-sm text-slate-600">
        {startDate} to {endDate}
      </p>

      <DevAuthBar onAuthChange={handleAuthChange} />

      <div className="mb-4 flex gap-4 text-sm">
        <span className="rounded border border-blue-200 bg-blue-50 px-2 py-1">
          Parent A
        </span>
        <span className="rounded border border-emerald-200 bg-emerald-50 px-2 py-1">
          Parent B
        </span>
        <span className="rounded border px-2 py-1 ring-2 ring-amber-500">
          Override
        </span>
      </div>

      {isLoading ? <p>Loading schedule...</p> : null}
      {error ? <p className="text-red-600">{error}</p> : null}
      {!isLoading && !error ? (
        <CalendarGrid
          days={days}
          monthStartDate={startDate}
          onDaySelect={setSelectedDay}
        />
      ) : null}

      {selectedDay ? (
        <div className="mt-6">
          <OverrideForm
            initialDate={selectedDay.current_date}
            createOverride={createOverrideRequest}
            onSuccess={() => {
              setSelectedDay(null);
              void refetch();
            }}
          />
        </div>
      ) : null}
    </main>
  );
}
