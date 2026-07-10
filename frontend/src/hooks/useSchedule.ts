"use client";

import { useCallback, useEffect, useState } from "react";

import type { FetchSchedule } from "@/lib/api/schedule";
import { api } from "@/lib/api/client";
import type { DailyCustodyState } from "@/lib/types";

interface UseScheduleOptions {
  startDate: string;
  endDate: string;
  authToken?: string | null;
  fetchSchedule?: FetchSchedule;
}

interface UseScheduleResult {
  days: DailyCustodyState[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
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

export function useSchedule({
  startDate,
  endDate,
  authToken = null,
  fetchSchedule = defaultFetchSchedule,
}: UseScheduleOptions): UseScheduleResult {
  const [days, setDays] = useState<DailyCustodyState[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!authToken) {
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const result = await fetchSchedule({
        start_date: startDate,
        end_date: endDate,
      });
      setDays(result);
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "Failed to load schedule.",
      );
    } finally {
      setIsLoading(false);
    }
  }, [authToken, endDate, fetchSchedule, startDate]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { days, isLoading, error, refetch };
}
