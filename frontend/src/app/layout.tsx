import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Custody Scheduler",
  description: "2-2-3 custody schedule calendar",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
