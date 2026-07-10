import { api } from "@/lib/api/client";
import type { CreateOverride } from "@/lib/api/schedule";
import type { ScheduleOverride } from "@/lib/types";

export const createOverrideRequest: CreateOverride = async (override) => {
  const { data, error, response } = await api.POST("/api/v1/schedule/overrides", {
    body: override,
  });

  if (response.status === 403) {
    const detail =
      typeof error === "object" && error && "detail" in error
        ? String((error as { detail: unknown }).detail)
        : "Action restricted to Parent roles only.";
    return { ok: false, status: 403, detail };
  }

  if (!response.ok || !data) {
    return { ok: false, status: response.status };
  }

  return { ok: true, data: data as ScheduleOverride };
};
