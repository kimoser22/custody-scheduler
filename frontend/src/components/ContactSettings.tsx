"use client";

import { FormEvent, useEffect, useState } from "react";

import type { FetchMe, MeProfile, UpdateMe } from "@/lib/api/me";

interface ContactSettingsProps {
  fetchMe: FetchMe;
  updateMe: UpdateMe;
}

export function ContactSettings({ fetchMe, updateMe }: ContactSettingsProps) {
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    void fetchMe()
      .then((profile: MeProfile) => {
        if (cancelled) {
          return;
        }
        setPhone(profile.phone ?? "");
        setEmail(profile.email ?? "");
      })
      .catch((loadError: unknown) => {
        if (cancelled) {
          return;
        }
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Failed to load contact settings.",
        );
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [fetchMe]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    setSuccess(false);

    const trimmedPhone = phone.trim();
    if (!trimmedPhone) {
      setIsSubmitting(false);
      setError("Phone is required.");
      return;
    }

    const result = await updateMe({
      phone: trimmedPhone,
      email: email.trim() ? email.trim() : null,
    });

    setIsSubmitting(false);

    if (!result.ok) {
      setError(result.detail ?? "Unable to save contact settings.");
      return;
    }

    setPhone(result.data.phone ?? "");
    setEmail(result.data.email ?? "");
    setSuccess(true);
  }

  if (isLoading) {
    return <p className="text-sm text-slate-600">Loading contact settings...</p>;
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded border p-4">
      <h2 className="text-lg font-semibold">Contact settings</h2>
      <p className="text-sm text-slate-600">
        SMS uses your phone number; override emails go to this address. Text
        STOP to opt out of SMS; START to resume.
      </p>
      <label className="block text-sm">
        Phone
        <input
          aria-label="Phone"
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
          className="mt-1 block w-full rounded border px-2 py-1"
          autoComplete="tel"
        />
      </label>
      <label className="block text-sm">
        Email
        <input
          aria-label="Email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="mt-1 block w-full rounded border px-2 py-1"
          autoComplete="email"
        />
      </label>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {success ? (
        <p className="text-sm text-emerald-700">Contact settings saved.</p>
      ) : null}
      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded bg-slate-800 px-3 py-2 text-white disabled:opacity-50"
      >
        Save contacts
      </button>
    </form>
  );
}
