import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Knowledge — news with the background",
  description: "News cards with the history behind them, and short lessons from open sources.",
};

const NAV = [
  { href: "/", label: "News" },
  { href: "/learn", label: "Learn" },
  { href: "/saved", label: "Saved" },
  { href: "/quality", label: "Quality" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="sticky top-0 z-20 border-b border-line bg-paper/90 backdrop-blur">
          <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
            <Link href="/" className="card-title text-xl font-semibold tracking-tight">
              Knowledge
            </Link>
            <nav className="flex gap-1 text-sm">
              {NAV.map((item) => (
                <Link key={item.href} href={item.href} className="rounded-full px-3 py-1.5 text-muted hover:bg-accent-soft hover:text-ink">
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-3xl px-4 pb-24 pt-6">{children}</main>
      </body>
    </html>
  );
}
