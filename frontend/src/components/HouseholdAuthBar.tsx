"use client";

import { useEffect, useState } from "react";

import {
  type Identity,
  type LoginFn,
  type Session,
  IDENTITY_USER_IDS,
  clearSession,
  getSession,
  login,
} from "@/lib/auth";

interface HouseholdAuthBarProps {
  onAuthChange?: () => void;
  loginFn?: LoginFn;
}

const IDENTITIES: Identity[] = ["Viewer", "Parent A", "Parent B"];

/** Friendly label for the signed-in strip — never expose raw user ids. */
export function householdDisplayLabel(
  session: Session,
  selectedIdentity?: Identity,
): string {
  if (
    selectedIdentity &&
    IDENTITY_USER_IDS[selectedIdentity] === session.userId
  ) {
    return selectedIdentity;
  }
  for (const identity of IDENTITIES) {
    if (IDENTITY_USER_IDS[identity] === session.userId) {
      return identity;
    }
  }
  return session.role;
}

export function HouseholdAuthBar({
  onAuthChange,
  loginFn,
}: HouseholdAuthBarProps) {
  const [identity, setIdentity] = useState<Identity>("Viewer");
  const [passcode, setPasscode] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const existing = getSession();
    if (existing) {
      setSession(existing);
      onAuthChange?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSignIn(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    const result = await login(IDENTITY_USER_IDS[identity], passcode, loginFn);

    setIsSubmitting(false);

    if (!result.ok || !result.session) {
      setError(result.detail ?? "Sign in failed.");
      return;
    }

    setSession(result.session);
    setPasscode("");
    onAuthChange?.();
  }

  function handleSignOut() {
    clearSession();
    setSession(null);
    setError(null);
    onAuthChange?.();
  }

  if (session) {
    const label = householdDisplayLabel(session, identity);
    return (
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded border border-slate-200 bg-white p-3 text-sm">
        <span className="font-medium text-slate-800">Household</span>
        <span className="text-slate-700">Signed in as {label}</span>
        <button
          type="button"
          onClick={handleSignOut}
          className="rounded border border-slate-200 px-3 py-1 text-slate-700 hover:bg-slate-50"
        >
          Sign out
        </button>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSignIn}
      className="mb-4 flex flex-wrap items-center gap-3 rounded border border-slate-200 bg-white p-3 text-sm"
    >
      <span className="font-medium text-slate-800">Household</span>
      <label htmlFor="household-member" className="text-slate-600">
        Household member
      </label>
      <select
        id="household-member"
        aria-label="Household member"
        value={identity}
        onChange={(event) => setIdentity(event.target.value as Identity)}
        className="rounded border border-slate-200 px-2 py-1"
      >
        {IDENTITIES.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <label htmlFor="household-passcode" className="text-slate-600">
        Passcode
      </label>
      <input
        id="household-passcode"
        aria-label="Passcode"
        type="password"
        value={passcode}
        onChange={(event) => setPasscode(event.target.value)}
        className="rounded border border-slate-200 px-2 py-1"
      />
      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50"
      >
        Sign in
      </button>
      <span className="text-slate-600">Not signed in</span>
      {error ? <span className="text-red-600">{error}</span> : null}
    </form>
  );
}
