import fs from "node:fs";
import path from "node:path";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, Github } from "lucide-react";
import { docsLinkResolver, renderMarkdown } from "@/lib/markdown";

/* A guide from the repository's docs/ folder, rendered at build time.
 *
 * The Markdown files are the source: the site reads ../docs/<file> during
 * `next build` (tools/deploy.py --website and `npm run build` both run in
 * oreo.elixpo/ inside the repository checkout), so the website and GitHub
 * always show the same text. Edit docs/<file>, not this page.
 */

const REPO = "https://github.com/elixpo/oreo";

/** Guides rendered on the site; links between them stay on the site. */
export const SITE_DOCS: Record<string, string> = {
  "CLI.md": "/docs/cli/",
  "USB.md": "/docs/usb/",
  "TRANSFER.md": "/docs/transfer/",
};

const OVERVIEWS: Record<string, string> = {
  "APPS.md": "/docs/apps/",
};

export type QuickLink = { label: string; href: string };
export type Related = { href: string; title: string; description: string };

export function readRepoDoc(file: string): string {
  const full = path.join(process.cwd(), "..", "docs", file);
  if (!fs.existsSync(full)) {
    throw new Error(
      `docs/${file} not found at ${full}: build the site from oreo.elixpo/ inside the OreoOS repository`,
    );
  }
  return fs.readFileSync(full, "utf8");
}

export default function RepoDoc({
  file, chip, icon: Icon, title, lead, quickLinks = [], related = [],
}: {
  file: string;
  chip: string;
  icon: LucideIcon;
  title: string;
  lead: string;
  quickLinks?: QuickLink[];
  related?: Related[];
}) {
  const doc = renderMarkdown(readRepoDoc(file), docsLinkResolver(SITE_DOCS, OVERVIEWS));
  const toc = doc.headings.filter((h) => h.level === 2);

  return (
    <div className="relative">
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[480px] overflow-hidden">
        <div className="absolute left-1/4 top-0 h-[320px] w-[320px] rounded-full bg-primary/[0.08] blur-[120px]" />
        <div className="absolute right-1/4 top-20 h-[260px] w-[260px] rounded-full bg-teal/[0.10] blur-[120px]" />
      </div>

      <div className="container-page pt-16 pb-28">
        <span className="chip mb-6">
          <Icon className="h-3 w-3 text-primary" /> {chip}
        </span>
        <h1 className="max-w-3xl font-display text-4xl leading-[1.05] tracking-tight sm:text-5xl">
          {title}
        </h1>
        <p className="mt-5 max-w-2xl text-text-dim">{lead}</p>

        <div className="mt-8 flex flex-wrap items-center gap-2">
          {quickLinks.map((q) => (
            <a key={q.href} href={q.href}
               className="rounded-full border border-border px-3 py-1 text-sm text-text-dim transition-colors hover:border-primary/50 hover:text-text">
              {q.label}
            </a>
          ))}
          <a href={`${REPO}/blob/main/docs/${file}`} target="_blank" rel="noreferrer"
             className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1 text-sm text-text-dim transition-colors hover:border-primary/50 hover:text-text">
            <Github className="h-3.5 w-3.5" /> docs/{file}
          </a>
        </div>

        <div className="mt-12 grid gap-12 lg:grid-cols-[220px_minmax(0,1fr)]">
          <aside className="hidden lg:block">
            <nav aria-label="On this page" className="sticky top-24 max-h-[calc(100vh-8rem)] overflow-y-auto text-sm">
              <p className="mb-3 font-display text-xs uppercase tracking-widest text-muted">On this page</p>
              <ul className="space-y-2 border-l border-border pl-4">
                {toc.map((h) => (
                  <li key={h.id}>
                    <a href={`#${h.id}`} className="text-text-dim transition-colors hover:text-primary">
                      {h.text}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </aside>

          <div className="min-w-0 max-w-3xl">
            <article className="text-[15px] text-text-dim" dangerouslySetInnerHTML={{ __html: doc.html }} />

            <p className="mt-16 text-sm text-muted">
              This page is built from{" "}
              <a href={`${REPO}/blob/main/docs/${file}`} target="_blank" rel="noreferrer"
                 className="text-primary underline decoration-primary/40 underline-offset-2">
                docs/{file}
              </a>{" "}
              in the OreoOS repository. Corrections are welcome there.
            </p>

            {related.length > 0 && (
              <div className="mt-10 grid gap-4 sm:grid-cols-2">
                {related.map((r) => (
                  <Link key={r.href} href={r.href} className="card-surface group p-5 hover:border-primary/50">
                    <p className="font-display text-lg">{r.title}</p>
                    <p className="mt-2 text-sm text-text-dim">{r.description}</p>
                    <span className="mt-4 inline-flex items-center gap-2 text-sm text-primary">
                      Read
                      <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
