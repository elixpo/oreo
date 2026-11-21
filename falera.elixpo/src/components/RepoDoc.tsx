import fs from "node:fs";
import path from "node:path";
import Link from "next/link";
import type { ReactNode } from "react";
import { Github } from "lucide-react";
import { PageHeader, Section } from "@/components/ui";
import { HACK_GUIDES } from "@/data/hacks";
import { mermaidDrawing } from "@/lib/diagrams";
import { renderMarkdown, repoLinkResolver } from "@/lib/markdown";

/* A Markdown file from the repository, rendered at build time.
 *
 * The Markdown files are the source: the site reads ../<file> during
 * `next build` (tools/deploy.py --website and `npm run build` both run in
 * falera.elixpo/ inside the repository checkout), so the website and GitHub
 * always show the same text. Edit the Markdown file, not the page.
 */

const REPO = "https://github.com/elixpo/falera";

/** Repository files rendered on the site; links between them stay on the site. */
export const SITE_DOCS: Record<string, string> = {
  "docs/CLI.md": "/docs/cli/",
  "docs/USB.md": "/docs/usb/",
  "docs/TRANSFER.md": "/docs/transfer/",
  "docs/hacks/README.md": "/hacks/",
  "CONTRIBUTING.md": "/contribute/",
  ...Object.fromEntries(HACK_GUIDES.map((h) => [`docs/hacks/${h.doc}`, `/hacks/${h.slug}/`])),
};

const OVERVIEWS: Record<string, string> = {
  "docs/APPS.md": "/docs/apps/",
};

export type QuickLink = { label: string; href: string };
export type Related = { href: string; title: string; description: string };

/** Read a file by its path in the repository ("docs/CLI.md"). */
export function readRepoDoc(file: string): string {
  const full = path.join(process.cwd(), "..", file);
  if (!fs.existsSync(full)) {
    throw new Error(
      `${file} not found at ${full}: build the site from falera.elixpo/ inside the FaleraOS repository`,
    );
  }
  return fs.readFileSync(full, "utf8");
}

export default function RepoDoc({
  file, chip, title, lead, quickLinks = [], related = [], children,
  bodyTitle,
}: {
  /** Path in the repository, e.g. "docs/CLI.md" or "CONTRIBUTING.md". */
  file: string;
  /** The eyebrow above the title. */
  chip: string;
  title: ReactNode;
  lead: string;
  quickLinks?: QuickLink[];
  related?: Related[];
  /** Shown between the header and the document (e.g. cards). */
  children?: ReactNode;
  /** A heading above the rendered document, when `children` come first. */
  bodyTitle?: string;
}) {
  const dir = path.posix.dirname(file) === "." ? "" : path.posix.dirname(file);
  const doc = renderMarkdown(
    readRepoDoc(file),
    repoLinkResolver(dir, SITE_DOCS, OVERVIEWS),
    { diagram: mermaidDrawing },
  );
  const toc = doc.headings.filter((h) => h.level === 2);

  return (
    <>
      <PageHeader eyebrow={chip} title={title} lede={lead}>
        {quickLinks.map((q) => (
          <a key={q.href} href={q.href} className="chip transition-colors hover:border-text/50 hover:text-text">
            {q.label}
          </a>
        ))}
        <a href={`${REPO}/blob/main/${file}`} target="_blank" rel="noreferrer"
           className="chip transition-colors hover:border-text/50 hover:text-text">
          <Github className="h-3 w-3" aria-hidden="true" /> {file}
        </a>
      </PageHeader>

      {children && <Section>{children}</Section>}

      <Section>
        {bodyTitle && <h2 className="h-title mb-10">{bodyTitle}</h2>}

        <div className="grid gap-12 lg:grid-cols-[13rem_minmax(0,1fr)]">
          <aside className="hidden lg:block">
            <nav aria-label="On this page" className="sticky top-[calc(var(--header-h)+2rem)] max-h-[calc(100vh-8rem)] overflow-y-auto text-sm">
              <p className="label mb-4">On this page</p>
              <ul className="space-y-2.5 border-l border-border pl-4">
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
            <article className="text-[0.975rem] text-text-dim [&>*:first-child]:mt-0" dangerouslySetInnerHTML={{ __html: doc.html }} />

            <p className="mt-16 border-t border-border pt-6 text-sm text-muted">
              This page is built from{" "}
              <a href={`${REPO}/blob/main/${file}`} target="_blank" rel="noreferrer" className="link">
                {file}
              </a>{" "}
              in the FaleraOS repository. Corrections are welcome there.
            </p>

            {related.length > 0 && (
              <div className="mt-10 grid gap-4 sm:grid-cols-2">
                {related.map((r) => (
                  <Link key={r.href} href={r.href} className="card-link group block p-6">
                    <p className="h-card group-hover:text-primary">{r.title}</p>
                    <p className="mt-2 text-sm leading-relaxed text-text-dim">{r.description}</p>
                    <span className="link-onward mt-4">Read <span aria-hidden="true">→</span></span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </Section>
    </>
  );
}
