import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "FlakeHunter",
  description: "Find flaky tests in CI and fix them with a verified AI agent.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} font-sans antialiased`}>
        <header className="border-b border-border bg-surface">
          <nav className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <span
                aria-hidden
                className="grid h-6 w-6 place-items-center rounded-md bg-accent text-xs text-white"
              >
                FH
              </span>
              FlakeHunter
            </Link>
            <div className="flex gap-4 text-sm text-muted">
              <Link href="/" className="hover:text-text">
                Repositories
              </Link>
              <Link href="/evals" className="hover:text-text">
                Evals
              </Link>
            </div>
          </nav>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{children}</main>
      </body>
    </html>
  );
}
