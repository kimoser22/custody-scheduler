"use client";

import { useState } from "react";

import type { EnsureCalendarFeed } from "@/lib/api/calendarFeed";

interface CalendarSubscribeProps {
  ensureCalendarFeed: EnsureCalendarFeed;
}

export function CalendarSubscribe({
  ensureCalendarFeed,
}: CalendarSubscribeProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [isBusy, setIsBusy] = useState(false);

  async function loadFeed(rotate: boolean) {
    setIsBusy(true);
    setError(null);
    setCopied(false);
    const result = await ensureCalendarFeed({ rotate });
    setIsBusy(false);
    if (!result.ok) {
      setError(result.detail ?? "Unable to create calendar feed link.");
      return;
    }
    setUrl(result.data.url);
  }

  async function handleCopy() {
    if (!url) {
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setError("Could not copy to clipboard.");
    }
  }

  return (
    <div className="space-y-3 rounded border p-4">
      <h2 className="text-lg font-semibold">Calendar subscribe</h2>
      <p className="text-sm text-slate-600">
        Add this private link in Apple Calendar, Google Calendar, or Outlook.
        Rotate it if the link was shared by mistake.
      </p>
      {url ? (
        <label className="block text-sm">
          Subscribe URL
          <input
            aria-label="Subscribe URL"
            readOnly
            value={url}
            className="mt-1 block w-full rounded border px-2 py-1 font-mono text-xs"
          />
        </label>
      ) : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {copied ? (
        <p className="text-sm text-emerald-700">Copied subscribe URL.</p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={isBusy}
          onClick={() => void loadFeed(false)}
          className="rounded bg-slate-800 px-3 py-2 text-white disabled:opacity-50"
        >
          {url ? "Show link" : "Create link"}
        </button>
        {url ? (
          <>
            <button
              type="button"
              disabled={isBusy}
              onClick={() => void handleCopy()}
              className="rounded border px-3 py-2 disabled:opacity-50"
            >
              Copy link
            </button>
            <button
              type="button"
              disabled={isBusy}
              onClick={() => void loadFeed(true)}
              className="rounded border px-3 py-2 disabled:opacity-50"
            >
              Rotate link
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
}
