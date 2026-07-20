"use client";

import { useState } from "react";

import {
  type Identity,
  type LoginFn,
  type Session,
  IDENTITY_USER_IDS,
  clearSession,
  login,
} from "@/lib/auth";

interface DevAuthBarProps {
  onAuthChange?: () => void;
  loginFn?: LoginFn;
}

const IDENTITIES: Identity[] = ["Viewer", "Parent A", "Parent B"];

export function DevAuthBar({ onAuthChange, loginFn }: DevAuthBarProps) {
  const [identity, setIdentity] = useState<Identity>("Viewer");
  const [passcode, setPasscode] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

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

  return (
    <form
      onSubmit={handleSignIn}
      className="mb-4 flex flex-wrap items-center gap-3 rounded border bg-slate-50 p-3 text-sm"
    >
      <span className="font-medium">Sign in</span>
      <label htmlFor="dev-identity">Identity</label>
      <select
        id="dev-identity"
        aria-label="Identity"
        value={identity}
        onChange={(event) => setIdentity(event.target.value as Identity)}
        className="rounded border px-2 py-1"
      >
        {IDENTITIES.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <label htmlFor="dev-passcode">Passcode</label>
      <input
        id="dev-passcode"
        aria-label="Passcode"
        type="password"
        value={passcode}
        onChange={(event) => setPasscode(event.target.value)}
        className="rounded border px-2 py-1"
      />
      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50"
      >
        Sign in
      </button>
      {session ? (
        <>
          <span className="text-slate-600">
            Signed in as {session.role} (user {session.userId})
          </span>
          <button
            type="button"
            onClick={handleSignOut}
            className="rounded border px-3 py-1"
          >
            Sign out
          </button>
        </>
      ) : (
        <span className="text-slate-600">Not signed in</span>
      )}
      {error ? <span className="text-red-600">{error}</span> : null}
    </form>
  );
}
