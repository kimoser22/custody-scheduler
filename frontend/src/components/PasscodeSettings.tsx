"use client";

import { FormEvent, useState } from "react";

import type { ChangePasscode } from "@/lib/api/me";

const MIN_PASSCODE_LENGTH = 4;

interface PasscodeSettingsProps {
  changePasscode: ChangePasscode;
}

export function PasscodeSettings({ changePasscode }: PasscodeSettingsProps) {
  const [currentPasscode, setCurrentPasscode] = useState("");
  const [newPasscode, setNewPasscode] = useState("");
  const [confirmPasscode, setConfirmPasscode] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(false);

    if (newPasscode.length < MIN_PASSCODE_LENGTH) {
      setError(`New passcode must be at least ${MIN_PASSCODE_LENGTH} characters.`);
      return;
    }
    if (newPasscode !== confirmPasscode) {
      setError("New passcode and confirmation do not match.");
      return;
    }

    setIsSubmitting(true);
    const result = await changePasscode({
      current_passcode: currentPasscode,
      new_passcode: newPasscode,
    });
    setIsSubmitting(false);

    if (!result.ok) {
      setError(result.detail ?? "Unable to change passcode.");
      return;
    }

    setCurrentPasscode("");
    setNewPasscode("");
    setConfirmPasscode("");
    setSuccess(true);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded border p-4">
      <h2 className="text-lg font-semibold">Passcode settings</h2>
      <p className="text-sm text-slate-600">
        Change your login passcode. You will need the current one to confirm.
      </p>
      <label className="block text-sm">
        Current passcode
        <input
          aria-label="Current passcode"
          type="password"
          value={currentPasscode}
          onChange={(event) => setCurrentPasscode(event.target.value)}
          className="mt-1 block w-full rounded border px-2 py-1"
          autoComplete="current-password"
        />
      </label>
      <label className="block text-sm">
        New passcode
        <input
          aria-label="New passcode"
          type="password"
          value={newPasscode}
          onChange={(event) => setNewPasscode(event.target.value)}
          className="mt-1 block w-full rounded border px-2 py-1"
          autoComplete="new-password"
        />
      </label>
      <label className="block text-sm">
        Confirm new passcode
        <input
          aria-label="Confirm new passcode"
          type="password"
          value={confirmPasscode}
          onChange={(event) => setConfirmPasscode(event.target.value)}
          className="mt-1 block w-full rounded border px-2 py-1"
          autoComplete="new-password"
        />
      </label>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {success ? (
        <p className="text-sm text-emerald-700">Passcode updated.</p>
      ) : null}
      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded bg-slate-800 px-3 py-2 text-white disabled:opacity-50"
      >
        Change passcode
      </button>
    </form>
  );
}
