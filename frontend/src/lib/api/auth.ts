import { api } from "@/lib/api/client";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  role: string;
}

export interface LoginOutcome {
  ok: boolean;
  status: number;
  data?: LoginResponse;
  detail?: string;
}

function errorDetail(error: unknown, fallback: string): string {
  return typeof error === "object" && error && "detail" in error
    ? String((error as { detail: unknown }).detail)
    : fallback;
}

export async function loginRequest(
  userId: number,
  passcode: string,
): Promise<LoginOutcome> {
  const { data, error, response } = await api.POST("/api/v1/auth/token", {
    body: { user_id: userId, passcode },
  });

  if (!response.ok || !data) {
    return {
      ok: false,
      status: response.status,
      detail: errorDetail(error, "Invalid credentials."),
    };
  }

  return { ok: true, status: 200, data: data as LoginResponse };
}
