"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FUND_URL, GITHUB } from "@/lib/links";

const NAV = [
  { href: "/badge/",       label: "Badge" },
  { href: "/apps/",        label: "Apps" },
  { href: "/get-started/", label: "Get started" },
  { href: "/docs/",        label: "Docs" },
  { href: "/rv565/",       label: "RV565" },
  { href: "/contribute/",  label: "Contribute" },
  { href: "/supporters/",  label: "Support" },
];

// Pages that live under another nav item.
const SECTION_OF: [string, string][] = [
  ["/hacks/", "/docs/"],
  ["/paper/", "/rv565/"],
  ["/docs/video-architecture/", "/rv565/"],
];

function GithubIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M12 .5C5.65.5.5 5.65.5 12a11.5 11.5 0 0 0 7.86 10.92c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.52-1.33-1.28-1.69-1.28-1.69-1.05-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.41-2.7 5.38-5.26 5.67.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5z" />
    </svg>
  );
}

/* Sticky header: logo, the main routes, GitHub and "Fund the badge".
 * Below lg the routes fold into a <details> menu, which opens and closes
 * without JavaScript; the only script here marks the current page and
 * closes the menu after a navigation. */
export default function Header() {
  const pathname = usePathname() ?? "/";
  const menu = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    if (menu.current) menu.current.open = false;
  }, [pathname]);

  const section = SECTION_OF.find(([p]) => pathname.startsWith(p))?.[1];
  const current = (href: string) => pathname.startsWith(href) || section === href;

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/95 backdrop-blur supports-[backdrop-filter]:bg-bg/85">
      <div className="container-page flex h-[var(--header-h)] items-center justify-between gap-4">
        <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label="Falera, home">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/favicon-48x48.png" alt="" width={28} height={28} className="h-7 w-7" />
          <span className="flex items-baseline gap-2">
            <b className="text-[0.95rem] tracking-tight">Falera</b>
            <small className="hidden text-xs text-muted xl:inline">FaleraOS · Elixpo</small>
          </span>
        </Link>

        <nav aria-label="Main" className="hidden lg:block">
          <ul className="flex items-center gap-6 text-[0.8125rem] font-semibold">
            {NAV.map((n) => (
              <li key={n.href}>
                <Link
                  href={n.href}
                  aria-current={current(n.href) ? "page" : undefined}
                  className={`py-2 transition-colors hover:text-primary ${
                    current(n.href) ? "text-primary" : "text-text"
                  }`}
                >
                  {n.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex items-center gap-2">
          <a
            href={GITHUB}
            target="_blank"
            rel="noreferrer"
            aria-label="FaleraOS on GitHub"
            className="hidden h-10 w-10 items-center justify-center rounded-pill text-text transition-colors hover:bg-bg-raised sm:inline-flex"
          >
            <GithubIcon />
          </a>
          <a
            href={FUND_URL}
            target="_blank"
            rel="noreferrer"
            className="btn-accent min-h-[40px] px-4 py-2 text-[0.8125rem]"
          >
            Fund the badge
          </a>

          <details ref={menu} className="group relative lg:hidden">
            <summary
              className="flex h-10 w-10 cursor-pointer list-none items-center justify-center rounded-pill border border-border
                         [&::-webkit-details-marker]:hidden"
              aria-label="Menu"
            >
              <svg viewBox="0 0 20 20" className="h-4 w-4 group-open:hidden" aria-hidden="true">
                <path d="M3 6h14M3 10h14M3 14h14" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
              </svg>
              <svg viewBox="0 0 20 20" className="hidden h-4 w-4 group-open:block" aria-hidden="true">
                <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
              </svg>
            </summary>
            <nav
              aria-label="Main"
              className="fixed inset-x-0 top-[var(--header-h)] max-h-[calc(100dvh-var(--header-h))] overflow-y-auto
                         border-b border-border bg-bg"
            >
              <ul className="container-page grid gap-1 py-4 text-base font-semibold">
                <li>
                  <Link href="/" aria-current={pathname === "/" ? "page" : undefined}
                        className={`block rounded-inner px-3 py-3 hover:bg-bg-raised ${pathname === "/" ? "text-primary" : ""}`}>
                    Home
                  </Link>
                </li>
                {NAV.map((n) => (
                  <li key={n.href}>
                    <Link
                      href={n.href}
                      aria-current={current(n.href) ? "page" : undefined}
                      className={`block rounded-inner px-3 py-3 hover:bg-bg-raised ${current(n.href) ? "text-primary" : ""}`}
                    >
                      {n.label}
                    </Link>
                  </li>
                ))}
                <li className="mt-2 border-t border-border pt-3">
                  <a href={GITHUB} target="_blank" rel="noreferrer"
                     className="flex items-center gap-2 rounded-inner px-3 py-3 hover:bg-bg-raised">
                    <GithubIcon /> GitHub <span aria-hidden="true">↗</span>
                  </a>
                </li>
              </ul>
            </nav>
          </details>
        </div>
      </div>
    </header>
  );
}
