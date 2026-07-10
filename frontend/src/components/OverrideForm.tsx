"use client";

import { FormEvent, useState } from "react";

import type { CreateOverride } from "@/lib/api/schedule";
import type { ParentRole, ScheduleOverride } from "@/lib/types";
import { PARENT_A, PARENT_B } from "@/lib/types";

interface OverrideFormProps {
  initialDate: string;
  createOverride: CreateOverride;
  onSuccess?: () => void;
}

const DEFAULT_OVERRIDE: Omit<ScheduleOverride, "override_date"> = {
  assigned_parent: PARENT_A,
  override_type: "Holiday",
  description: "",
  is_active: true,
};

export function OverrideForm({
  initialDate,
  createOverride,
  onSuccess,
}: OverrideFormProps) {
  const [assignedParent, setAssignedParent] = useState<ParentRole>(PARENT_A);
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    const result = await createOverride({
      override_date: initialDate,
      assigned_parent: assignedParent,
      override_type: "Holiday",
      description,
      is_active: true,
    });

    setIsSubmitting(false);

    if (!result.ok) {
      setError(result.detail ?? "Unable to save override.");
      return;
    }

    onSuccess?.();
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded border p-4">
      <h2 className="text-lg font-semibold">Add override for {initialDate}</h2>
      <label className="block text-sm">
        Assigned parent
        <select
          aria-label="Assigned parent"
          value={assignedParent}
          onChange={(event) => setAssignedParent(event.target.value as ParentRole)}
          className="mt-1 block w-full rounded border px-2 py-1"
        >
          <option value={PARENT_A}>{PARENT_A}</option>
          <option value={PARENT_B}>{PARENT_B}</option>
        </select>
      </label>
      <label className="block text-sm">
        Description
        <input
          aria-label="Description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="mt-1 block w-full rounded border px-2 py-1"
        />
      </label>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
      >
        Save override
      </button>
    </form>
  );
}
