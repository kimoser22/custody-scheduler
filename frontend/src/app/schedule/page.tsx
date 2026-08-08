"use client";

import { useEffect, useState } from "react";

import { HouseholdAuthBar } from "@/components/HouseholdAuthBar";
import { CalendarGrid } from "@/components/CalendarGrid";
import { CalendarSubscribe } from "@/components/CalendarSubscribe";
import { ContactSettings } from "@/components/ContactSettings";
import { LegalFooter } from "@/components/LegalFooter";
import { OverrideForm } from "@/components/OverrideForm";
import { PasscodeSettings } from "@/components/PasscodeSettings";
import { PendingOverrides } from "@/components/PendingOverrides";
import { RecordsExport } from "@/components/RecordsExport";
import {
  AccountSettings,
  AccountSettingsSection,
} from "@/components/AccountSettings";
import { useSchedule } from "@/hooks/useSchedule";
import { ensureCalendarFeedRequest } from "@/lib/api/calendarFeed";
import { downloadFamilyExportRequest } from "@/lib/api/export";
import {
  changePasscodeRequest,
  fetchMeRequest,
  updateMeRequest,
} from "@/lib/api/me";
import {
  createOverrideRequest,
  decideOverrideRequest,
  fetchPendingOverridesRequest,
  sweepExpiredOverridesRequest,
} from "@/lib/api/overrides";
import {
  type Session,
  canRequestOverride,
  currentUserId as currentUserIdFrom,
  getSession,
} from "@/lib/auth";
import { getMonthRange, localTodayDate, shiftMonth } from "@/lib/calendar";
import type { DailyCustodyState } from "@/lib/types";

export default function SchedulePage() {
  const [monthReference, setMonthReference] = useState(() => new Date());
  const { startDate, endDate } = getMonthRange(monthReference);
  const todayDate = localTodayDate();
  const [session, setSession] = useState<Session | null>(null);
  const authToken = session?.token ?? null;
  const { days, isLoading, error, refetch, prefetch } = useSchedule({
    startDate,
    endDate,
    authToken,
  });
  const [selectedDay, setSelectedDay] = useState<DailyCustodyState | null>(null);
  const [pendingListVersion, setPendingListVersion] = useState(0);
  const currentUserId = currentUserIdFrom(session);
  const showOverrideForm = selectedDay != null && canRequestOverride(session);
  const todayCustody = !isLoading && !error
    ? days.find((day) => day.current_date === todayDate)
    : undefined;
  const viewingOtherMonth = !isLoading && !error && todayCustody == null;

  // Warm the neighboring months once the current one has data, so Previous /
  // Next render instantly from cache instead of flashing a spinner.
  useEffect(() => {
    if (!authToken || isLoading) {
      return;
    }
    void prefetch(getMonthRange(shiftMonth(monthReference, -1)));
    void prefetch(getMonthRange(shiftMonth(monthReference, 1)));
  }, [authToken, isLoading, monthReference, prefetch]);

  function handleAuthChange() {
    setSession(getSession());
  }

  function handleDaySelect(day: DailyCustodyState) {
    if (!canRequestOverride(getSession())) {
      setSelectedDay(null);
      return;
    }
    setSelectedDay(day);
  }

  function jumpToThisMonth() {
    setSelectedDay(null);
    setMonthReference(new Date());
  }

  return (
    <main className="mx-auto max-w-5xl p-4 sm:p-6">
      <h1 className="mb-2 text-2xl font-bold">Custody Schedule</h1>
      <div className="sticky top-0 z-10 -mx-4 mb-4 space-y-1 border-b border-slate-200 bg-white/95 px-4 py-2 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
          <button
            type="button"
            aria-label="Previous month"
            className="min-h-11 min-w-11 rounded border px-3"
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
            className="min-h-11 min-w-11 rounded border px-3"
            onClick={() => {
              setSelectedDay(null);
              setMonthReference((current) => shiftMonth(current, 1));
            }}
          >
            Next
          </button>
        </div>
        {todayCustody ? (
          <p className="text-sm font-medium text-slate-800">
            Today: {todayCustody.final_parent}
          </p>
        ) : null}
        {viewingOtherMonth ? (
          <button
            type="button"
            className="text-sm font-medium text-slate-800 underline-offset-2 hover:underline"
            onClick={jumpToThisMonth}
          >
            Today · Jump to this month
          </button>
        ) : null}
      </div>

      <HouseholdAuthBar onAuthChange={handleAuthChange} />

      {authToken ? (
        <div className="mt-4 mb-4">
          <AccountSettings showContacts={canRequestOverride(session)}>
            <AccountSettingsSection id="calendar" title="Calendar subscribe">
              <CalendarSubscribe
                key={authToken}
                ensureCalendarFeed={ensureCalendarFeedRequest}
              />
            </AccountSettingsSection>
            <AccountSettingsSection id="passcode" title="Passcode">
              <PasscodeSettings
                key={`passcode-${authToken}`}
                changePasscode={changePasscodeRequest}
              />
            </AccountSettingsSection>
            <AccountSettingsSection id="download" title="Download records">
              <RecordsExport
                key={`export-${authToken}`}
                downloadFamilyExport={downloadFamilyExportRequest}
              />
            </AccountSettingsSection>
            <AccountSettingsSection
              id="contacts"
              title="Contact settings"
              parentOnly
            >
              <ContactSettings
                key={authToken ?? "signed-out"}
                fetchMe={fetchMeRequest}
                updateMe={updateMeRequest}
              />
            </AccountSettingsSection>
          </AccountSettings>
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap gap-4 text-sm">
        <span className="rounded border border-blue-200 bg-blue-50 px-2 py-1">
          Parent A
        </span>
        <span className="rounded border border-emerald-200 bg-emerald-50 px-2 py-1">
          Parent B
        </span>
        <span className="rounded border px-2 py-1 ring-2 ring-amber-500">
          Holiday / override
        </span>
        <span className="rounded border-2 border-slate-800 px-2 py-1">
          Today
        </span>
      </div>

      {isLoading ? <p>Loading schedule...</p> : null}
      {error ? <p className="text-red-600">{error}</p> : null}
      {!isLoading && !error ? (
        <CalendarGrid
          days={days}
          monthStartDate={startDate}
          todayDate={todayDate}
          onDaySelect={handleDaySelect}
        />
      ) : null}

      {authToken ? (
        <div className="mt-6">
          <PendingOverrides
            key={authToken}
            refreshSignal={pendingListVersion}
            fetchPendingOverrides={fetchPendingOverridesRequest}
            decideOverride={decideOverrideRequest}
            sweepExpiredOverrides={
              canRequestOverride(session)
                ? sweepExpiredOverridesRequest
                : undefined
            }
            currentUserId={currentUserId}
            onDecided={() => void refetch()}
          />
        </div>
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

      <LegalFooter />
    </main>
  );
}
