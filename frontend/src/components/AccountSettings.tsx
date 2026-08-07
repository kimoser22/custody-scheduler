"use client";

import {
  createContext,
  useContext,
  useId,
  useState,
  type ReactNode,
} from "react";

interface AccountSettingsContextValue {
  showContacts: boolean;
}

const AccountSettingsContext = createContext<AccountSettingsContextValue>({
  showContacts: true,
});

interface AccountSettingsProps {
  children: ReactNode;
  /** When false, sections marked parentOnly are omitted (Viewer). Default true. */
  showContacts?: boolean;
}

export function AccountSettings({
  children,
  showContacts = true,
}: AccountSettingsProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <AccountSettingsContext.Provider value={{ showContacts }}>
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
  /** Hide for Viewer when AccountSettings showContacts is false. */
  parentOnly?: boolean;
}

export function AccountSettingsSection({
  id,
  title,
  children,
  parentOnly = false,
}: AccountSettingsSectionProps) {
  const { showContacts } = useContext(AccountSettingsContext);

  if (parentOnly && !showContacts) {
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
