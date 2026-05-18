"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Github, Star, GitFork } from "lucide-react";

const NAV = [
  { href: "/",            label: "Home" },
  { href: "/get-started/",label: "Get Started" },
  { href: "/badge/",      label: "Badge" },
  { href: "/apps/",       label: "Apps" },
  { href: "/hacks/",      label: "Hacks" },
  { href: "/contribute/", label: "Contribute" },
];

export default function Header() {
  const pathname = usePathname();

  return (
    <motion.header
      initial={{ y: -16, opacity: 0 }}
      animate={{ y:   0, opacity: 1 }}
      transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
      className="sticky top-0 z-40 border-b border-border/60 bg-bg/80
                 backdrop-blur supports-[backdrop-filter]:bg-bg/60"
    >
      <div className="container-page flex h-16 items-center justify-between">
        {/* Logo + wordmark */}
        <Link href="/" className="group flex items-center gap-3">
          <div className="relative h-9 w-9 overflow-hidden rounded-md
                          border border-primary/40 bg-bg-raised
                          shadow-[0_0_24px_rgba(255,93,104,0.25)]">
            <div className="absolute inset-0 grid place-items-center
                            font-display text-lg text-primary">
              o
            </div>
          </div>
          <span className="font-display text-2xl tracking-tight">
            Oreo
          </span>
        </Link>

        {/* Centre nav */}
        <nav className="hidden items-center gap-1 md:flex">
          {NAV.map((n) => {
            const active =
              n.href === "/"
                ? pathname === "/"
                : pathname?.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={`relative rounded-md px-3 py-2 text-sm uppercase
                            tracking-widest transition-colors
                            ${active ? "text-text" : "text-muted hover:text-text"}`}
              >
                {n.label}
                {active ? (
                  <motion.span
                    layoutId="nav-underline"
                    className="absolute inset-x-3 -bottom-px h-px bg-primary"
                    transition={{ type: "spring", stiffness: 340, damping: 28 }}
                  />
                ) : null}
              </Link>
            );
          })}
        </nav>

        {/* GitHub badge */}
        <a
          href="https://github.com/elixpo/oreo"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-3 rounded-md border border-border
                     bg-bg-raised px-3 py-2 text-xs text-text-dim
                     transition-colors hover:border-primary/60 hover:text-text"
        >
          <Github className="h-4 w-4" />
          <div className="flex flex-col leading-tight">
            <span className="font-semibold text-text">elixpo/oreo</span>
            <span className="flex items-center gap-2 text-muted">
              <Star className="h-3 w-3" /> 446
              <GitFork className="h-3 w-3" /> 140
            </span>
          </div>
        </a>
      </div>
    </motion.header>
  );
}
