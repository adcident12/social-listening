import type { ReactNode } from "react";
import { Noto_Sans_Thai } from "next/font/google";
import Nav from "@/components/Nav";
import "./globals.css";

export const metadata = { title: "Social Listening" };

const notoSansThai = Noto_Sans_Thai({
  subsets: ["thai", "latin"],
  variable: "--font-noto-thai",
  display: "swap",
});

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="th" className={notoSansThai.variable}>
      <body className="min-h-screen bg-neutral-50 text-neutral-900 antialiased">
        <Nav />
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
