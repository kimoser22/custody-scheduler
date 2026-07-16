"use client";

import { useState } from "react";

import { CalendarGrid } from "@/components/CalendarGrid";
import { DevAuthBar } from "@/components/DevAuthBar";
import { OverrideForm } from "@/components/OverrideForm";
import { PendingOverrides } from "@/components/PendingOverrides";
import { useSchedule } from "@/hooks/useSchedule";
import {
  createOverrideRequest,
  decideOverrideRequest,
  fetchPendingOverridesRequest,
} from "@/lib/api/overrides";
import {
  canRequestOverride,
  getAuthToken,
  userIdFromToken,
} from "@/lib/auth";
import { getMonthRange, shiftMonth } from "@/lib/calendar";
import type { DailyCustodyState } from "@/lib/types";

export default function SchedulePage() {
  const [monthReference, setMonthReference] = useState(() => new Date());
  const { startDate, endDate } = getMonthRange(monthReference);
  const [authToken, setAuthTokenState] = useState<string | null>(null);
  const { days, isLoading, error, refetch } = useSchedule({
    startDate,
    endDate,
    authToken,
  });
  const [selectedDay, setSelectedDay] = useState<DailyCustodyState | null>(null);
  const [pendingListVersion, setPendingListVersion] = useState(0);
  const currentUserId = userIdFromToken(authToken);
  const showOverrideForm = selectedDay != null && canRequestOverride(authToken);

  function handleAuthChange() {
    setAuthTokenState(getAuthToken());
  }

  function handleDaySelect(day: DailyCustodyState) {
    if (!canRequestOverride(getAuthToken())) {
      setSelectedDay(null);
      return;
    }
    setSelectedDay(day);
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="mb-2 text-2xl font-bold">Custody Schedule</h1>
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
        <button
          type="button"
          aria-label="Previous month"
          className="rounded border px-2 py-1"
          onClick={() => {
            setSelectedDay(null);
            setMonthReference((current) => shiftMonth(current, -1));
          }}
        >
          Previous
        </button>
        <p>
          {startDate} to {endDate}
        </p>
        <button
          type="button"
          aria-label="Next month"
          className="rounded border px-2 py-1"
          onClick={() => {
            setSelectedDay(null);
            setMonthReference((current) => shiftMonth(current, 1));
          }}
        >
          Next
        </button>
      </div>

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
          onDaySelect={handleDaySelect}
        />
      ) : null}

      {showOverrideForm && selectedDay ? (
        <div className="mt-6">
          <OverrideForm
            initialDate={selectedDay.current_date}
            createOverride={createOverrideRequest}
            onSuccess={() => {
              setSelectedDay(null);
              void refetch();
              setPendingListVersion((version) => version + 1);
            }}
          />
        </div>
      ) : null}

      {authToken ? (
        <div className="mt-6">
          <PendingOverrides
            key={`${authToken}-${pendingListVersion}`}
            fetchPendingOverrides={fetchPendingOverridesRequest}
            decideOverride={decideOverrideRequest}
            currentUserId={currentUserId}
            onDecided={() => void refetch()}
          />
        </div>
      ) : null}
    </main>
  );
}
