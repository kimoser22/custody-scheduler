import { api } from "@/lib/api/client";

export interface MeProfile {
  id: number;
  role: string;
  custody_label: string | null;
  phone: string | null;
  email: string | null;
}

export interface MeUpdate {
  phone?: string | null;
  email?: string | null;
}

export interface PasscodeChange {
  current_passcode: string;
  new_passcode: string;
}

export type FetchMe = () => Promise<MeProfile>;

export type UpdateMe = (
  update: MeUpdate,
) => Promise<{ ok: true; data: MeProfile } | { ok: false; status: number; detail?: string }>;

export type ChangePasscode = (
  change: PasscodeChange,
) => Promise<{ ok: true } | { ok: false; status: number; detail?: string }>;

function errorDetail(error: unknown, fallback: string): string {
  return typeof error === "object" && error && "detail" in error
    ? String((error as { detail: unknown }).detail)
    : fallback;
}

export async function fetchMeRequest(): Promise<MeProfile> {
  const { data, error, response } = await api.GET("/api/v1/me");
  if (!response.ok || !data) {
    throw new Error(errorDetail(error, "Failed to load contact settings."));
  }
  return data as MeProfile;
}

export async function updateMeRequest(
  update: MeUpdate,
): Promise<{ ok: true; data: MeProfile } | { ok: false; status: number; detail?: string }> {
  const { data, error, response } = await api.PATCH("/api/v1/me", {
    body: update,
  });

  if (!response.ok || !data) {
    return {
      ok: false,
      status: response.status,
      detail: errorDetail(error, "Unable to save contact settings."),
    };
  }

  return { ok: true, data: data as MeProfile };
}

export async function changePasscodeRequest(
  change: PasscodeChange,
): Promise<{ ok: true } | { ok: false; status: number; detail?: string }> {
  const { data, error, response } = await api.PATCH("/api/v1/me/passcode", {
    body: change,
  });

  if (!response.ok || !data) {
    return {
      ok: false,
      status: response.status,
      detail: errorDetail(error, "Unable to change passcode."),
    };
  }

  return { ok: true };
}
