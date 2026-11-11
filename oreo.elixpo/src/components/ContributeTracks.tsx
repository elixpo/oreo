"use client";

import { motion } from "framer-motion";
import { Bug, BookOpen, Code2, ExternalLink, GitPullRequest } from "lucide-react";

const NEW_ISSUE = "https://github.com/elixpo/oreo/issues/new?template=";

/* The four contribution paths on /contribute. Each card opens its GitHub
 * issue form (.github/ISSUE_TEMPLATE/<form>); the small link is the guide
 * to read first. */
const TRACKS = [
  { Icon: Code2, title: "Write an app", form: "app_proposal.yml",
    body: "Propose the idea, the controls and whether it belongs in the App Store or ships built in. Start with oreo new and the app guide.",
    guide: { label: "App guide", href: "/docs/apps/" },
    tint: "text-primary" },
  { Icon: Bug, title: "Fix a bug", form: "bug_report.yml",
    body: "Report it with the OreoOS version from oreo info, the oreo doctor output and the steps. Or pick a good first issue.",
    guide: { label: "Good first issues", href: "https://github.com/elixpo/oreo/issues?q=is%3Aopen+label%3A%22good+first+issue%22" },
    tint: "text-teal" },
  { Icon: BookOpen, title: "Write a hack", form: "hack_proposal.yml",
    body: "Say what it shows and what hardware it needs, then write one Markdown file in docs/hacks/. Merged hacks get a page on /hacks.",
    guide: { label: "The hacks", href: "/hacks/" },
    tint: "text-gold" },
  { Icon: GitPullRequest, title: "Improve the OS", form: "os_improvement.yml",
    body: "Name the area, the problem and your proposal, and which OS and CLI contract it touches, before a large change.",
    guide: { label: "AGENTS.md", href: "https://github.com/elixpo/oreo/blob/main/AGENTS.md" },
    tint: "text-lilac" },
] as const;

export default function ContributeTracks() {
  return (
    <div className="mt-12 grid gap-5 sm:grid-cols-2">
      {TRACKS.map((t, i) => {
        const external = /^https?:/.test(t.guide.href);
        return (
          <motion.div
            key={t.title}
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ delay: 0.05 * i, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            whileHover={{ y: -4 }}
            className="card-surface group relative flex items-start gap-4 p-6 hover:border-primary/40"
          >
            <div className={`grid h-11 w-11 shrink-0 place-items-center rounded-md bg-card-sub ${t.tint}`}>
              <t.Icon className="h-5 w-5" />
            </div>
            <div className="flex-1">
              <h3 className="font-display text-lg leading-tight">
                {/* The title link covers the whole card (after:inset-0). */}
                <a href={NEW_ISSUE + t.form} target="_blank" rel="noreferrer"
                   className="after:absolute after:inset-0 after:content-['']">
                  {t.title}
                </a>
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-text-dim">{t.body}</p>
              <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-muted">
                <span className="inline-flex items-center gap-1 transition-colors group-hover:text-primary">
                  Open the form <ExternalLink className="h-3 w-3" />
                </span>
                <a href={t.guide.href}
                   {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
                   className="relative z-10 underline decoration-border underline-offset-2 transition-colors hover:text-primary">
                  {t.guide.label}
                </a>
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
