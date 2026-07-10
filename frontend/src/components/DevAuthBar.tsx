"use client";

import { useEffect, useState } from "react";

import {
  ensureAuthToken,
  getAuthToken,
  setParentToken,
  setViewerToken,
} from "@/lib/auth";

type DevIdentity = "Viewer" | "Parent A" | "Parent B";

interface DevAuthBarProps {
  onAuthChange?: () => void;
}

function identityFromToken(token: string): DevIdentity {
  if (token === "parent:a") return "Parent A";
  if (token === "parent:b") return "Parent B";
  return "Viewer";
}

export function DevAuthBar({ onAuthChange }: DevAuthBarProps) {
  const [identity, setIdentity] = useState<DevIdentity>("Viewer");
  const [token, setToken] = useState("");

  useEffect(() => {
    const activeToken = ensureAuthToken();
    setIdentity(identityFromToken(activeToken));
    setToken(activeToken);
    onAuthChange?.();
  }, [onAuthChange]);

  function handleIdentityChange(nextIdentity: DevIdentity) {
    if (nextIdentity === "Parent A") {
      setParentToken("a");
    } else if (nextIdentity === "Parent B") {
      setParentToken("b");
    } else {
      setViewerToken();
    }
    setIdentity(nextIdentity);
    setToken(getAuthToken() ?? "");
    onAuthChange?.();
  }

  return (
    <div className="mb-4 flex items-center gap-3 rounded border bg-slate-50 p-3 text-sm">
      <span className="font-medium">Dev auth</span>
      <label htmlFor="dev-identity">Identity</label>
      <select
        id="dev-identity"
        aria-label="Identity"
        value={identity}
        onChange={(event) => handleIdentityChange(event.target.value as DevIdentity)}
        className="rounded border px-2 py-1"
      >
        <option value="Viewer">Viewer</option>
        <option value="Parent A">Parent A</option>
        <option value="Parent B">Parent B</option>
      </select>
      <span className="text-slate-600">Token: {token}</span>
    </div>
  );
}
