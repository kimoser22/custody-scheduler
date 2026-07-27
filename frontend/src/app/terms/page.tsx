import Link from "next/link";

import { TermsBody } from "@/components/TermsBody";
import { TERMS_BODY, TERMS_TITLE } from "@/lib/legal-copy";

export const metadata = {
  title: `${TERMS_TITLE} | Custody Scheduler`,
};

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-2xl p-6">
      <p className="mb-4 text-sm">
        <Link href="/schedule" className="underline text-slate-600">
          Back to schedule
        </Link>
      </p>
      <h1 className="mb-4 text-2xl font-bold">{TERMS_TITLE}</h1>
      <TermsBody body={TERMS_BODY} />
    </main>
  );
}
