"use client";

import { useCallback, useEffect, useState } from "react";

import type { DecideOverride, FetchPendingOverrides } from "@/lib/api/schedule";
import type { ScheduleOverride } from "@/lib/types";

interface PendingOverridesProps {
  fetchPendingOverrides: FetchPendingOverrides;
  decideOverride: DecideOverride;
  onDecided?: () => void;
}

export function PendingOverrides({
  fetchPendingOverrides,
  decideOverride,
  onDecided,
}: PendingOverridesProps) {
  const [requests, setRequests] = useState<ScheduleOverride[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [decisionErrors, setDecisionErrors] = useState<Record<number, string>>({});
  const [pendingDecisionId, setPendingDecisionId] = useState<number | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await fetchPendingOverrides();
      setRequests(result);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Failed to load pending override requests.",
      );
    } finally {
      setIsLoading(false);
    }
  }, [fetchPendingOverrides]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  async function handleDecision(overrideId: number, approve: boolean) {
    setPendingDecisionId(overrideId);
    setDecisionErrors((previous) => {
      const next = { ...previous };
      delete next[overrideId];
      return next;
    });

    const result = await decideOverride(overrideId, approve);

    setPendingDecisionId(null);

    if (!result.ok) {
      setDecisionErrors((previous) => ({
        ...previous,
        [overrideId]: result.detail ?? "Unable to record decision.",
      }));
      return;
    }

    onDecided?.();
    await refetch();
  }

  if (isLoading) {
    return <p>Loading pending override requests...</p>;
  }

  if (error) {
    return <p className="text-red-600">{error}</p>;
  }

  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Pending override requests</h2>
      {requests.length === 0 ? (
        <p className="text-sm text-slate-600">No pending override requests.</p>
      ) : (
        <ul className="space-y-2">
          {requests.map((request) => (
            <li key={request.id} className="rounded border p-3 text-sm">
              <div className="font-medium">
                {request.override_date} &mdash; {request.assigned_parent} (
                {request.override_type})
              </div>
              <div className="text-slate-600">{request.description}</div>
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  disabled={pendingDecisionId === request.id}
                  onClick={() => request.id != null && handleDecision(request.id, true)}
                  className="rounded bg-emerald-600 px-3 py-1 text-white disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  type="button"
                  disabled={pendingDecisionId === request.id}
                  onClick={() => request.id != null && handleDecision(request.id, false)}
                  className="rounded bg-red-600 px-3 py-1 text-white disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
              {request.id != null && decisionErrors[request.id] ? (
                <p className="mt-1 text-red-600">{decisionErrors[request.id]}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
