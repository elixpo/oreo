"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, Github, Menu, Star, X } from "lucide-react";
import { useGithubStats } from "@/lib/useGithubStats";

const NAV = [
  { href: "/",             label: "Home" },
  { href: "/get-started/", label: "Get Started" },
  { href: "/badge/",       label: "Badge" },
  { href: "/apps/",        label: "Apps" },
  { href: "/docs/",        label: "Docs" },
  { href: "/supporters/",  label: "Supporters" },
];

// Everything else, under "More". External links open in a new tab.
type MoreLink = { href: string; label: string; external?: boolean };
const MORE: { title: string; links: MoreLink[] }[] = [
  {
    title: "Guides",
    links: [
      { href: "/docs/cli/",      label: "falera CLI" },
      { href: "/docs/transfer/", label: "Transfer files" },
      { href: "/docs/usb/",      label: "Connect over USB" },
      { href: "/docs/apps/",     label: "Build an app" },
      { href: "/hacks/",         label: "Hacks" },
    ],
  },
  {
    title: "RV565 video",
    links: [
      { href: "/paper/",                   label: "Research paper" },
      { href: "/rv565/convert/",           label: "Video converter" },
      { href: "/docs/video-architecture/", label: "Video architecture" },
    ],
  },
  {
    title: "Community",
    links: [
      { href: "/contribute/", label: "Contribute" },
      { href: "https://payouts.elixpo.com/f/oreo-badge", label: "Fund the badge", external: true },
      { href: "https://github.com/elixpo/falera/discussions", label: "Discussions", external: true },
    ],
  },
];
const MORE_LINKS = MORE.flatMap((g) => g.links);

function MoreItem({ link, className, onClick }: { link: MoreLink; className: string; onClick?: () => void }) {
  if (link.external) {
    return (
      <a href={link.href} target="_blank" rel="noreferrer" className={className} onClick={onClick}>
        {link.label} <span aria-hidden="true">↗</span>
      </a>
    );
  }
  return (
    <Link href={link.href} className={className} onClick={onClick}>
      {link.label}
    </Link>
  );
}

function fmtCount(n: number | null): string {
  if (n === null) return "–";
  if (n >= 10_000) return (n / 1000).toFixed(1) + "k";
  if (n >= 1000)   return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n);
}

// Floating pill header, following the Elixpo Research site: brand on the
// left, plain text navigation, and an ink GitHub pill on the right.
export default function Header() {
  const pathname = usePathname();
  const { stars } = useGithubStats();
  const [open, setOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);

  // Close the menus after navigating.
  useEffect(() => {
    setOpen(false);
    setMoreOpen(false);
  }, [pathname]);

  // Close "More" on a click outside it or on Escape.
  useEffect(() => {
    if (!moreOpen) return;
    const onDown = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setMoreOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMoreOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [moreOpen]);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname?.startsWith(href);
  // Docs stays underlined only on /docs/ itself when a docs page is under More.
  const navActive = (href: string) =>
    href === "/docs/" ? pathname === "/docs/" || pathname === "/docs" : isActive(href);
  const moreActive = MORE_LINKS.some((l) => !l.external && isActive(l.href));

  return (
    <header className="sticky top-3 z-40 mx-auto mt-3 w-[min(calc(100%-1.5rem),1510px)]">
      <div className="flex min-h-[64px] items-center justify-between gap-4 rounded-pill
                      border border-text/15 bg-bg/90 py-2 pl-4 pr-2
                      shadow-[0_18px_48px_rgba(20,32,24,0.09)] backdrop-blur-xl">
        <Link href="/" className="flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/favicon.ico" alt="" className="h-8 w-8 object-contain" loading="eager" decoding="async" />
          <span className="flex items-baseline gap-2">
            <b className="text-base">Falera</b>
            <small className="hidden text-xs text-muted sm:inline">FaleraOS · Elixpo</small>
          </span>
        </Link>

        <nav className="hidden items-center gap-6 text-xs font-semibold lg:flex">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              aria-current={navActive(n.href) ? "page" : undefined}
              className={`transition-opacity hover:opacity-55 ${
                navActive(n.href) ? "underline decoration-primary decoration-2 underline-offset-[6px]" : ""
              }`}
            >
              {n.label}
            </Link>
          ))}
          <div ref={moreRef} className="relative">
            <button
              type="button"
              onClick={() => setMoreOpen((v) => !v)}
              aria-expanded={moreOpen}
              aria-haspopup="true"
              className={`inline-flex items-center gap-1 transition-opacity hover:opacity-55 ${
                moreActive ? "underline decoration-primary decoration-2 underline-offset-[6px]" : ""
              }`}
            >
              More
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${moreOpen ? "rotate-180" : ""}`}
                           aria-hidden="true" />
            </button>
            {moreOpen && (
              <div className="absolute right-0 top-[calc(100%+14px)] grid w-[34rem] max-w-[calc(100vw-2rem)]
                              grid-cols-3 gap-4 rounded-[1.4rem] border border-text/15 bg-bg/95 p-5
                              shadow-[0_18px_48px_rgba(20,32,24,0.12)] backdrop-blur-xl">
                {MORE.map((g) => (
                  <div key={g.title} className="min-w-0">
                    <p className="mb-2 text-[11px] uppercase tracking-widest text-muted">{g.title}</p>
                    <ul className="grid gap-1">
                      {g.links.map((l) => (
                        <li key={l.href}>
                          <MoreItem
                            link={l}
                            onClick={() => setMoreOpen(false)}
                            className={`block rounded-md px-2 py-1.5 text-sm font-medium transition-colors
                                        hover:bg-bg-raised ${!l.external && isActive(l.href) ? "text-primary" : ""}`}
                          />
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        </nav>

        <div className="flex items-center gap-2">
          <a
            href="https://github.com/elixpo/falera"
            target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-pill bg-text px-4 py-3
                       text-xs font-bold text-bg transition-opacity hover:opacity-85"
            title={stars !== null ? `${stars} stars` : "GitHub"}
          >
            <Github className="h-4 w-4" />
            <span className="hidden sm:inline">GitHub</span>
            <span className="inline-flex items-center gap-1 opacity-75">
              <Star className="h-3 w-3" /> {fmtCount(stars)}
            </span>
          </a>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            className="inline-flex h-11 w-11 items-center justify-center rounded-pill
                       border border-border lg:hidden"
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {open && (
        <nav className="mt-2 grid gap-1 rounded-[1.4rem] border border-text/15 bg-bg/95 p-3
                        text-sm font-semibold shadow-[0_18px_48px_rgba(20,32,24,0.09)]
                        backdrop-blur-xl lg:hidden">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              aria-current={navActive(n.href) ? "page" : undefined}
              className={`rounded-pill px-4 py-2.5 ${navActive(n.href) ? "bg-bg-raised" : "hover:bg-bg-raised"}`}
            >
              {n.label}
            </Link>
          ))}
          {MORE.map((g) => (
            <div key={g.title} className="mt-2 border-t border-border pt-2">
              <p className="px-4 pb-1 pt-1 text-[11px] uppercase tracking-widest text-muted">{g.title}</p>
              {g.links.map((l) => (
                <MoreItem
                  key={l.href}
                  link={l}
                  className={`block rounded-pill px-4 py-2.5 ${
                    !l.external && isActive(l.href) ? "bg-bg-raised" : "hover:bg-bg-raised"
                  }`}
                />
              ))}
            </div>
          ))}
        </nav>
      )}
    </header>
  );
}
