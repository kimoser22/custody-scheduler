import createClient, { type Client } from "openapi-fetch";

import { getAuthToken } from "@/lib/auth";
import type { paths } from "@/lib/api/schema";

export function createApiClient(
  baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "",
): Client<paths> {
  const client = createClient<paths>({ baseUrl });

  client.use({
    onRequest({ request }) {
      const token = getAuthToken();
      if (token) {
        request.headers.set("Authorization", token);
      }
      return request;
    },
  });

  return client;
}

export const api = createApiClient();
