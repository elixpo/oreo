import Link from "next/link";
import { Github, Heart, Star, GitFork } from "lucide-react";

const COLUMNS = [
  {
    title: "Project",
    links: [
      { label: "Get Started", href: "/get-started/" },
      { label: "Badge",       href: "/badge/" },
      { label: "Apps",        href: "/apps/" },
      { label: "Hacks",       href: "/hacks/" },
      { label: "Contribute",  href: "/contribute/" },
      { label: "Upload",      href: "/upload/" },
    ],
  },
  {
    title: "Source",
    links: [
      { label: "OreoOS",       href: "https://github.com/elixpo/oreo",            external: true },
      { label: "Hardware",     href: "https://github.com/elixpo/oreo/tree/main/docs", external: true },
      { label: "Contributing", href: "https://github.com/elixpo/oreo/blob/main/CONTRIBUTING.md", external: true },
      { label: "License",      href: "https://github.com/elixpo/oreo/blob/main/LICENSE", external: true },
    ],
  },
  {
    title: "Community",
    links: [
      { label: "Contributors", href: "https://github.com/elixpo/oreo/graphs/contributors", external: true },
      { label: "Issues",       href: "https://github.com/elixpo/oreo/issues", external: true },
      { label: "Changelog",    href: "https://github.com/elixpo/oreo/blob/main/CHANGELOG.md", external: true },
      { label: "Code of Conduct", href: "https://github.com/elixpo/oreo/blob/main/CODE_OF_CONDUCT.md", external: true },
    ],
  },
];

export default function Footer() {
  return (
    <footer className="mt-32 border-t border-border/60 bg-bg-raised/40">
      <div className="container-page py-16">
        <div className="grid gap-12 sm:grid-cols-2 lg:grid-cols-4">
          {/* Brand block */}
          <div>
            <div className="mb-3 flex items-center gap-2">
              <div className="grid h-8 w-8 place-items-center rounded-md
                              border border-primary/40 bg-bg
                              font-display text-primary">o</div>
              <span className="font-display text-xl">Oreo</span>
            </div>
            <p className="text-sm leading-relaxed text-text-dim">
              Python OS, conference badge, app store, OTA. Open hardware,
              open firmware, open everything.
            </p>
            <a
              href="https://github.com/elixpo/oreo"
              target="_blank" rel="noreferrer"
              className="mt-5 inline-flex items-center gap-3 rounded-md
                         border border-border bg-bg-raised/60 px-3 py-2 text-xs
                         text-text-dim transition-colors
                         hover:border-primary/60 hover:text-text"
            >
              <Github className="h-4 w-4" />
              <span className="flex flex-col leading-tight">
                <span className="font-semibold text-text">elixpo/oreo</span>
                <span className="flex items-center gap-2 text-muted">
                  <Star className="h-3 w-3" /> 446
                  <GitFork className="h-3 w-3" /> 140
                </span>
              </span>
            </a>
          </div>

          {/* Link columns */}
          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h4 className="mb-3 text-xs uppercase tracking-widest text-muted">
                {col.title}
              </h4>
              <ul className="space-y-2 text-sm">
                {col.links.map((l) => (
                  <li key={l.href}>
                    {l.external ? (
                      <a
                        href={l.href}
                        target="_blank" rel="noreferrer"
                        className="text-text-dim transition-colors hover:text-text"
                      >
                        {l.label}
                      </a>
                    ) : (
                      <Link
                        href={l.href}
                        className="text-text-dim transition-colors hover:text-text"
                      >
                        {l.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col items-start justify-between
                        gap-3 border-t border-border/60 pt-6
                        text-xs text-muted sm:flex-row sm:items-center">
          <p>© 2026 Elixpo · MIT (code) + trademark carve-out</p>
          <p className="flex items-center gap-1.5">
            Built with <Heart className="h-3 w-3 text-primary" /> on MicroPython.
          </p>
        </div>
      </div>
    </footer>
  );
}
