"use client";

import { useEffect, useState } from "react";

import {
  ensureAuthToken,
  getAuthToken,
  setParentToken,
  setViewerToken,
} from "@/lib/auth";

type DevRole = "Parent" | "Viewer";

interface DevAuthBarProps {
  onAuthChange?: () => void;
}

export function DevAuthBar({ onAuthChange }: DevAuthBarProps) {
  const [role, setRole] = useState<DevRole>("Viewer");
  const [token, setToken] = useState("");

  useEffect(() => {
    const activeToken = ensureAuthToken();
    setRole(activeToken.startsWith("parent:") ? "Parent" : "Viewer");
    setToken(activeToken);
    onAuthChange?.();
  }, [onAuthChange]);

  function handleRoleChange(nextRole: DevRole) {
    if (nextRole === "Parent") {
      setParentToken();
    } else {
      setViewerToken();
    }
    setRole(nextRole);
    setToken(getAuthToken() ?? "");
    onAuthChange?.();
  }

  return (
    <div className="mb-4 flex items-center gap-3 rounded border bg-slate-50 p-3 text-sm">
      <span className="font-medium">Dev auth</span>
      <label htmlFor="dev-role">Role</label>
      <select
        id="dev-role"
        aria-label="Role"
        value={role}
        onChange={(event) => handleRoleChange(event.target.value as DevRole)}
        className="rounded border px-2 py-1"
      >
        <option value="Viewer">Viewer</option>
        <option value="Parent">Parent</option>
      </select>
      <span className="text-slate-600">Token: {token}</span>
    </div>
  );
}
