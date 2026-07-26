import Link from "next/link";

export function LegalFooter() {
  return (
    <footer className="mt-8 border-t pt-4 text-sm text-slate-600">
      <nav className="flex gap-4" aria-label="Legal">
        <Link href="/privacy" className="underline hover:text-slate-900">
          Privacy
        </Link>
        <Link href="/terms" className="underline hover:text-slate-900">
          Terms
        </Link>
      </nav>
    </footer>
  );
}
