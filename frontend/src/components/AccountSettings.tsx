"use client";

import {
  createContext,
  useContext,
  useId,
  useState,
  type ReactNode,
} from "react";

interface AccountSettingsContextValue {
  isParent: boolean;
}

const AccountSettingsContext = createContext<AccountSettingsContextValue>({
  isParent: true,
});

interface AccountSettingsProps {
  children: ReactNode;
  /** False for the shared Viewer account: sections marked parentOnly are
   * omitted. Renamed from showContacts — it now gates passcode and record
   * download too, not just contact settings. */
  isParent?: boolean;
}

export function AccountSettings({
  children,
  isParent = true,
}: AccountSettingsProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <AccountSettingsContext.Provider value={{ isParent }}>
      <div className="rounded border border-slate-200 bg-white">
        <button
          type="button"
          className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-slate-800 hover:bg-slate-50"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((current) => !current)}
        >
          <span>Account & settings</span>
          <span className="text-slate-500" aria-hidden="true">
            {open ? "▾" : "▸"}
          </span>
        </button>
        {open ? (
          <div
            id={panelId}
            className="space-y-4 border-t border-slate-200 p-4"
          >
            {children}
          </div>
        ) : null}
      </div>
    </AccountSettingsContext.Provider>
  );
}

interface AccountSettingsSectionProps {
  id: string;
  title: string;
  children: ReactNode;
  /** Omitted for the shared Viewer account. */
  parentOnly?: boolean;
}

export function AccountSettingsSection({
  id,
  title,
  children,
  parentOnly = false,
}: AccountSettingsSectionProps) {
  const { isParent } = useContext(AccountSettingsContext);

  if (parentOnly && !isParent) {
    return null;
  }

  return (
    <section aria-labelledby={`account-settings-${id}-heading`} className="space-y-2">
      {/*
        Visually hidden: child panels already ship their own headings.
        Kept in the DOM so accordion tests and screen readers get section labels.
      */}
      <h3 id={`account-settings-${id}-heading`} className="sr-only">
        {title}
      </h3>
      {children}
    </section>
  );
}
