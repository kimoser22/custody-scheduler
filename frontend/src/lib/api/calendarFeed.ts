import { api } from "@/lib/api/client";

export interface CalendarFeed {
  token: string;
  url: string;
}

export type EnsureCalendarFeed = (options?: {
  rotate?: boolean;
}) => Promise<
  { ok: true; data: CalendarFeed } | { ok: false; status: number; detail?: string }
>;

function errorDetail(error: unknown, fallback: string): string {
  return typeof error === "object" && error && "detail" in error
    ? String((error as { detail: unknown }).detail)
    : fallback;
}

export async function ensureCalendarFeedRequest(options?: {
  rotate?: boolean;
}): Promise<
  { ok: true; data: CalendarFeed } | { ok: false; status: number; detail?: string }
> {
  const { data, error, response } = await api.POST("/api/v1/me/calendar-feed", {
    body: { rotate: options?.rotate ?? false },
  });

  if (!response.ok || !data) {
    return {
      ok: false,
      status: response.status,
      detail: errorDetail(error, "Unable to create calendar feed link."),
    };
  }

  return { ok: true, data: data as CalendarFeed };
}
