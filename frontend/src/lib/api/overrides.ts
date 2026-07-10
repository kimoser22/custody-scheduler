import { api } from "@/lib/api/client";
import type { CreateOverride, DecideOverride, FetchPendingOverrides } from "@/lib/api/schedule";
import type { ScheduleOverride } from "@/lib/types";

function errorDetail(error: unknown, fallback: string): string {
  return typeof error === "object" && error && "detail" in error
    ? String((error as { detail: unknown }).detail)
    : fallback;
}

export const createOverrideRequest: CreateOverride = async (override) => {
  const { data, error, response } = await api.POST("/api/v1/schedule/overrides", {
    body: override,
  });

  if (response.status === 403) {
    return {
      ok: false,
      status: 403,
      detail: errorDetail(error, "Action restricted to Parent roles only."),
    };
  }

  if (!response.ok || !data) {
    return { ok: false, status: response.status };
  }

  return { ok: true, data: data as ScheduleOverride };
};

export const fetchPendingOverridesRequest: FetchPendingOverrides = async () => {
  const { data, error, response } = await api.GET("/api/v1/schedule/overrides/pending");

  if (error || !response.ok) {
    throw new Error("Failed to load pending override requests.");
  }

  return (data ?? []) as ScheduleOverride[];
};

export const decideOverrideRequest: DecideOverride = async (overrideId, approve) => {
  const { data, error, response } = await api.POST(
    "/api/v1/schedule/overrides/{override_id}/decision",
    {
      params: { path: { override_id: overrideId } },
      body: { approve },
    },
  );

  if (!response.ok || !data) {
    return {
      ok: false,
      status: response.status,
      detail: errorDetail(error, "Unable to record decision."),
    };
  }

  return { ok: true, data: data as ScheduleOverride };
};
