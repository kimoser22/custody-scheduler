"use client";

import { useState } from "react";

import type { DownloadFamilyExport } from "@/lib/api/export";

interface RecordsExportProps {
  downloadFamilyExport: DownloadFamilyExport;
}

export function RecordsExport({ downloadFamilyExport }: RecordsExportProps) {
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleDownload() {
    setIsBusy(true);
    setError(null);
    setSuccess(null);
    const result = await downloadFamilyExport();
    setIsBusy(false);
    if (!result.ok) {
      setError(result.detail ?? "Unable to download records.");
      return;
    }
    setSuccess(`Downloaded ${result.filename}.`);
  }

  return (
    <div className="space-y-3 rounded border p-4">
      <h2 className="text-lg font-semibold">Download records</h2>
      <p className="text-sm text-slate-600">
        Save a JSON archive of this family&apos;s baseline, overrides, audit
        history, and contacts. Store it off this device — the Fly volume is not
        a backup.
      </p>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {success ? <p className="text-sm text-emerald-700">{success}</p> : null}
      <button
        type="button"
        disabled={isBusy}
        onClick={() => void handleDownload()}
        className="rounded bg-slate-800 px-3 py-2 text-white disabled:opacity-50"
      >
        {isBusy ? "Downloading…" : "Download records"}
      </button>
    </div>
  );
}
