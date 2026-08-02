"use client";

import { FormEvent, useState } from "react";

import type { CreateOverride } from "@/lib/api/schedule";
import type { OverrideType, ParentRole } from "@/lib/types";
import { PARENT_A, PARENT_B } from "@/lib/types";

interface OverrideFormProps {
  initialDate: string;
  createOverride: CreateOverride;
  onSuccess?: () => void;
}

const OVERRIDE_TYPES: OverrideType[] = ["Holiday", "Mutual Swap", "Emergency"];

export function OverrideForm({
  initialDate,
  createOverride,
  onSuccess,
}: OverrideFormProps) {
  const [endDate, setEndDate] = useState(initialDate);
  const [assignedParent, setAssignedParent] = useState<ParentRole>(PARENT_A);
  const [overrideType, setOverrideType] = useState<OverrideType>("Holiday");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const rangeLabel =
    endDate && endDate !== initialDate
      ? `${initialDate} to ${endDate}`
      : initialDate;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    if (endDate < initialDate) {
      setIsSubmitting(false);
      setError("End date must be on or after the start date.");
      return;
    }

    const result = await createOverride({
      override_date: initialDate,
      end_date: endDate,
      assigned_parent: assignedParent,
      override_type: overrideType,
      description,
      is_active: false,
      status: "Pending",
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
      <h2 className="text-lg font-semibold">Request override for {rangeLabel}</h2>
      <p className="text-sm text-slate-600">
        The other parent will need to approve this before it takes effect.
      </p>
      <label className="block text-sm">
        End date
        <input
          aria-label="End date"
          type="date"
          value={endDate}
          min={initialDate}
          onChange={(event) => setEndDate(event.target.value)}
          className="mt-1 block w-full rounded border px-2 py-1"
        />
      </label>
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
        Override type
        <select
          aria-label="Override type"
          value={overrideType}
          onChange={(event) => setOverrideType(event.target.value as OverrideType)}
          className="mt-1 block w-full rounded border px-2 py-1"
        >
          {OVERRIDE_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
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
        Request override
      </button>
    </form>
  );
}
