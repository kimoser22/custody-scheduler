import { getAuthToken } from "@/lib/auth";

export type DownloadFamilyExport = () => Promise<
  { ok: true; filename: string } | { ok: false; status: number; detail?: string }
>;

function parseFilename(contentDisposition: string | null): string {
  if (!contentDisposition) {
    return "custody-export.json";
  }
  const match = /filename="([^"]+)"/.exec(contentDisposition);
  return match?.[1] ?? "custody-export.json";
}

/** Trigger a browser download of the family JSON archive. */
export async function downloadFamilyExportRequest(): Promise<
  { ok: true; filename: string } | { ok: false; status: number; detail?: string }
> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
  const token = getAuthToken();
  const response = await fetch(`${baseUrl}/api/v1/schedule/export.json`, {
    headers: token ? { Authorization: token } : {},
  });

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      detail = undefined;
    }
    return {
      ok: false,
      status: response.status,
      detail: detail ?? "Unable to download records.",
    };
  }

  const blob = await response.blob();
  const filename = parseFilename(response.headers.get("Content-Disposition"));
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
  return { ok: true, filename };
}
