"use client";

import { useCallback, useEffect, useState } from "react";

import type {
  DecideOverride,
  FetchPendingOverrides,
  SweepExpiredOverrides,
} from "@/lib/api/schedule";
import { formatExpiryLabel } from "@/lib/formatExpiry";
import {
  formatOverrideRange,
  overrideTypeLabel,
} from "@/lib/formatOverrideDisplay";
import type { ScheduleOverride } from "@/lib/types";

interface PendingOverridesProps {
  fetchPendingOverrides: FetchPendingOverrides;
  decideOverride: DecideOverride;
  currentUserId: number | null;
  sweepExpiredOverrides?: SweepExpiredOverrides;
  onDecided?: () => void;
}

export function PendingOverrides({
  fetchPendingOverrides,
  decideOverride,
  currentUserId,
  sweepExpiredOverrides,
  onDecided,
}: PendingOverridesProps) {
  const [requests, setRequests] = useState<ScheduleOverride[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expiredNotice, setExpiredNotice] = useState<string | null>(null);
  const [decisionErrors, setDecisionErrors] = useState<Record<number, string>>({});
  const [pendingDecisionId, setPendingDecisionId] = useState<number | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      if (sweepExpiredOverrides) {
        try {
          await sweepExpiredOverrides();
        } catch {
          // Sweep is best-effort; pending list still loads.
        }
      }
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
  }, [fetchPendingOverrides, sweepExpiredOverrides]);

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
    setExpiredNotice(null);

    const result = await decideOverride(overrideId, approve);

    setPendingDecisionId(null);

    if (!result.ok) {
      if (result.status === 410) {
        setRequests((previous) =>
          previous.filter((request) => request.id !== overrideId),
        );
        setExpiredNotice("This request expired.");
        await refetch();
        return;
      }
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
      {expiredNotice ? (
        <p className="text-sm text-amber-800">{expiredNotice}</p>
      ) : null}
      {requests.length === 0 ? (
        <p className="text-sm text-slate-600">
          No pending requests. Expired ones drop off automatically after the
          approval window.
        </p>
      ) : (
        <ul className="space-y-2">
          {requests.map((request) => {
            const isOwnRequest =
              currentUserId != null &&
              request.requested_by_user_id != null &&
              request.requested_by_user_id === currentUserId;
            const requester =
              request.requested_by_label?.trim() ||
              (request.requested_by_user_id != null
                ? `user ${request.requested_by_user_id}`
                : null);
            const range = formatOverrideRange(
              request.override_date,
              request.end_date,
            );

            return (
              <li key={request.id} className="rounded border p-3 text-sm">
                <div className="font-medium">
                  {overrideTypeLabel(request.override_type)} ·{" "}
                  {request.assigned_parent}
                </div>
                <div className="text-slate-700">
                  {range.dateLine}
                  {range.dayCount != null ? (
                    <span className="text-slate-500">
                      {" "}
                      · {range.dayCount === 1
                        ? "1 day"
                        : `${range.dayCount} days`}
                    </span>
                  ) : null}
                </div>
                <div className="text-slate-600">{request.description}</div>
                {requester ? (
                  <div className="text-xs text-slate-600">
                    Requested by {requester}
                  </div>
                ) : null}
                {request.expires_at ? (
                  <div className="text-xs text-slate-600">
                    {formatExpiryLabel(request.expires_at)}
                  </div>
                ) : null}
                <div className="mt-2 flex items-center gap-2">
                  {isOwnRequest ? (
                    <p className="text-slate-600">Waiting for the other parent</p>
                  ) : (
                    <>
                      <button
                        type="button"
                        disabled={pendingDecisionId === request.id}
                        onClick={() =>
                          request.id != null && handleDecision(request.id, true)
                        }
                        className="rounded bg-emerald-600 px-3 py-1 text-white disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        disabled={pendingDecisionId === request.id}
                        onClick={() =>
                          request.id != null && handleDecision(request.id, false)
                        }
                        className="rounded bg-red-600 px-3 py-1 text-white disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </>
                  )}
                </div>
                {request.id != null && decisionErrors[request.id] ? (
                  <p className="mt-1 text-red-600">{decisionErrors[request.id]}</p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
