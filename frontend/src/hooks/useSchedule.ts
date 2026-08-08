"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { FetchSchedule } from "@/lib/api/schedule";
import { api } from "@/lib/api/client";
import type { DailyCustodyState } from "@/lib/types";

interface UseScheduleOptions {
  startDate: string;
  endDate: string;
  authToken?: string | null;
  fetchSchedule?: FetchSchedule;
}

interface ScheduleRange {
  startDate: string;
  endDate: string;
}

interface UseScheduleResult {
  days: DailyCustodyState[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  prefetch: (range: ScheduleRange) => Promise<void>;
}

async function defaultFetchSchedule({
  start_date,
  end_date,
}: {
  start_date: string;
  end_date: string;
}): Promise<DailyCustodyState[]> {
  const { data, error, response } = await api.GET("/api/v1/schedule/", {
    params: { query: { start_date, end_date } },
  });

  if (error || !response.ok) {
    throw new Error("Failed to load schedule.");
  }

  return (data ?? []) as DailyCustodyState[];
}

function rangeKey(startDate: string, endDate: string): string {
  return `${startDate}|${endDate}`;
}

export function useSchedule({
  startDate,
  endDate,
  authToken = null,
  fetchSchedule = defaultFetchSchedule,
}: UseScheduleOptions): UseScheduleResult {
  const [days, setDays] = useState<DailyCustodyState[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Per-range cache. A revisited month renders from here instantly while a
  // background fetch revalidates it, so navigation never blanks the grid.
  const cache = useRef<Map<string, DailyCustodyState[]>>(new Map());

  const load = useCallback(
    async ({ force }: { force: boolean }) => {
      if (!authToken) {
        setIsLoading(false);
        return;
      }

      const key = rangeKey(startDate, endDate);
      const cached = cache.current.get(key);
      const hasVisible = cached !== undefined || (force && days.length >= 0);

      // Show a spinner only when there is nothing to display yet. A cached hit
      // or a forced refresh keeps the current grid on screen and swaps in place.
      if (cached !== undefined) {
        setDays(cached);
        setIsLoading(false);
      } else if (!force) {
        setIsLoading(true);
      }
      setError(null);

      try {
        const result = await fetchSchedule({
          start_date: startDate,
          end_date: endDate,
        });
        cache.current.set(key, result);
        setDays(result);
      } catch (loadError) {
        // Never blank a populated grid: only surface the error when there was
        // nothing to fall back to (a cold load with no cached data).
        if (!hasVisible) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Failed to load schedule.",
          );
        }
      } finally {
        setIsLoading(false);
      }
    },
    [authToken, endDate, fetchSchedule, startDate, days.length],
  );

  const refetch = useCallback(async () => {
    // A mutation can affect any month (a multi-day override may span into an
    // adjacent one), so drop the whole cache and re-read the current range
    // without flipping to a spinner.
    cache.current.clear();
    await load({ force: true });
  }, [load]);

  const prefetch = useCallback(
    async (range: ScheduleRange) => {
      if (!authToken) {
        return;
      }
      const key = rangeKey(range.startDate, range.endDate);
      if (cache.current.has(key)) {
        return;
      }
      try {
        const result = await fetchSchedule({
          start_date: range.startDate,
          end_date: range.endDate,
        });
        cache.current.set(key, result);
      } catch {
        // Best effort — a failed warm just means that month loads on demand.
      }
    },
    [authToken, fetchSchedule],
  );

  useEffect(() => {
    void load({ force: false });
    // Intentionally keyed on the range/auth, not `load` (which also depends on
    // days.length); revalidation on range change is the desired trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authToken, startDate, endDate]);

  return { days, isLoading, error, refetch, prefetch };
}
