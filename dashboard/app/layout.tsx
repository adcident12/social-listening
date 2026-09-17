import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata = { title: "Social Listening" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="th">
      <body className="min-h-screen bg-white text-neutral-900 antialiased">
        <nav className="flex items-center gap-4 border-b px-6 py-3">
          <span className="mr-4 font-bold">Social Listening</span>
          <Link href="/">Trends</Link>
          <Link href="/posts">Posts</Link>
        </nav>
        <main className="mx-auto max-w-4xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
