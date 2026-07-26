import Link from "next/link";

import { PRIVACY_BODY, PRIVACY_TITLE } from "@/lib/legal-copy";

export const metadata = {
  title: `${PRIVACY_TITLE} | Custody Scheduler`,
};

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-2xl p-6">
      <p className="mb-4 text-sm">
        <Link href="/schedule" className="underline text-slate-600">
          Back to schedule
        </Link>
      </p>
      <h1 className="mb-4 text-2xl font-bold">{PRIVACY_TITLE}</h1>
      {PRIVACY_BODY.split("\n\n").map((paragraph) => (
        <p key={paragraph.slice(0, 32)} className="mb-4 text-slate-800 leading-relaxed">
          {paragraph}
        </p>
      ))}
    </main>
  );
}
