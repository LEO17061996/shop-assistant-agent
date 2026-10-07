import type { Metadata } from "next";
import { Fraunces, Instrument_Sans, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const fraunces = Fraunces({ variable: "--font-fraunces", subsets: ["latin"], axes: ["SOFT", "opsz"] });
const instrument = Instrument_Sans({ variable: "--font-instrument", subsets: ["latin", "latin-ext"] });
const jetbrains = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Kestrel Home — AI shopping assistant",
  description:
    "RAG + agent demo: a LangGraph shopping assistant with hybrid search, tool calling and an eval suite.",
};

const NAV = [
  { href: "/", label: "Assistant" },
  { href: "/eval", label: "Eval report" },
  { href: "/how-it-works", label: "How it works" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${instrument.variable} ${jetbrains.variable} h-full antialiased`}
    >
      <body className="relative min-h-full flex flex-col">
        <header className="relative z-10 border-b border-rule">
          <div className="mx-auto flex max-w-[1240px] flex-wrap items-end justify-between gap-x-8 gap-y-3 px-4 pt-5 pb-3 sm:px-6">
            <Link href="/" className="group">
              <span className="block font-mono text-[10px] uppercase tracking-[0.22em] text-ink-3">
                Demo store · est. 2026
              </span>
              <span className="font-display text-[28px] leading-none tracking-tight">
                Kestrel <em className="text-clay">Home</em>
              </span>
            </Link>
            <nav className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
              {NAV.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  className="text-ink-2 underline-offset-[6px] transition hover:text-ink hover:underline decoration-clay"
                >
                  {n.label}
                </Link>
              ))}
              <a
                href="https://github.com/LEO17061996/shop-assistant-agent"
                className="text-ink-2 underline-offset-[6px] hover:text-ink hover:underline decoration-clay"
              >
                GitHub ↗
              </a>
            </nav>
          </div>
        </header>
        <div className="relative z-10 flex flex-1 flex-col">{children}</div>
        <footer className="relative z-10 border-t border-rule">
          <p className="mx-auto max-w-[1240px] px-4 py-4 text-xs text-ink-3 sm:px-6">
            Fictional store built by Leo (Le Thanh Thuan) as a portfolio project. Product names, materials, sizes
            and photos: Amazon Berkeley Objects, CC BY 4.0. Prices, stock and orders are simulated.
          </p>
        </footer>
      </body>
    </html>
  );
}
