"use client";

import { motion } from "framer-motion";
import { Reveal, fadeUp, staggerContainer } from "@/components/MotionWrap";
import { GitPullRequest, Bug, BookOpen, Code2, Heart } from "lucide-react";

const TRACKS = [
  {
    icon: <Code2 className="h-5 w-5" />,
    title: "Write an app",
    body:
      "A manifest.json + main.py and you're in the drawer. Look at apps/snake/ or apps/badge/ for ~50-line templates. Submit a PR into apps_market/.",
    href: "https://github.com/elixpo/oreo/blob/main/CONTRIBUTING.md#building-an-app",
    tint: "primary",
  },
  {
    icon: <Bug className="h-5 w-5" />,
    title: "Fix a bug",
    body:
      "Open issues are labelled by area (os, store, ota, wifi, bt). 'good first issue' tags exist; pair them with a serial log and you'll merge fast.",
    href: "https://github.com/elixpo/oreo/issues",
    tint: "teal",
  },
  {
    icon: <BookOpen className="h-5 w-5" />,
    title: "Write a hack",
    body:
      "Notice something the badge can do that we haven't documented? Drop a Markdown file into docs/hacks/ and we'll feature it on /hacks.",
    href: "https://github.com/elixpo/oreo/tree/main/docs/hacks",
    tint: "gold",
  },
  {
    icon: <GitPullRequest className="h-5 w-5" />,
    title: "Improve the OS",
    body:
      "Performance work, polish, new services. The core lives in oreoOS/. Big changes: open a draft PR early so we can review the shape before the code is final.",
    href: "https://github.com/elixpo/oreo/blob/main/oreoOS",
    tint: "lilac",
  },
];

const RULES = [
  "MIT-licensed inbound contributions — DCO applies, no CLA.",
  "Match the existing comment style: explain WHY, not what.",
  "Squash before merging — one logical change per commit.",
  "If you touch the device boot path, paste a fresh serial log in the PR description.",
  "Be excellent to each other (Code of Conduct).",
];

export default function ContributePage() {
  return (
    <div className="container-page pt-16 pb-28">
      <motion.div initial="hidden" animate="visible" variants={staggerContainer}>
        <motion.span variants={fadeUp} className="chip mb-6">
          <Heart className="h-3 w-3 text-primary" /> made by humans, with humans
        </motion.span>
        <motion.h1
          variants={fadeUp}
          className="font-display text-4xl leading-[1.05] tracking-tight sm:text-5xl"
        >
          Contribute to Oreo.
          <br /><span className="text-primary">Bring snacks.</span>
        </motion.h1>
        <motion.p variants={fadeUp} className="mt-5 max-w-2xl text-text-dim">
          OreoOS is open: code, hardware, prompts, assets, the lot.
          Pick a lane below — or invent one. We merge fast and credit
          loudly.
        </motion.p>
      </motion.div>

      <div className="mt-14 grid gap-5 sm:grid-cols-2">
        {TRACKS.map((t, i) => (
          <motion.a
            key={t.title}
            href={t.href}
            target="_blank"
            rel="noreferrer"
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ delay: 0.05 * i, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            whileHover={{ y: -4 }}
            className="card-surface group flex items-start gap-4 p-6
                       hover:border-primary/40"
          >
            <div className={`grid h-11 w-11 shrink-0 place-items-center
                             rounded-md bg-card-sub text-${t.tint}`}>
              {t.icon}
            </div>
            <div>
              <h3 className="font-display text-lg leading-tight">{t.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-text-dim">{t.body}</p>
              <span className="mt-3 inline-block text-xs text-muted
                               transition-colors group-hover:text-primary">
                Get started →
              </span>
            </div>
          </motion.a>
        ))}
      </div>

      <Reveal>
        <div className="mt-16 rounded-lg border border-border bg-bg-raised/40 p-8">
          <h2 className="font-display text-2xl">House rules</h2>
          <ul className="mt-5 space-y-2 text-sm text-text-dim">
            {RULES.map((r) => (
              <li key={r} className="flex items-start gap-3">
                <span className="mt-2 inline-block h-1.5 w-1.5 rounded-full bg-primary" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
          <a
            href="https://github.com/elixpo/oreo/blob/main/CONTRIBUTING.md"
            target="_blank" rel="noreferrer"
            className="btn-primary mt-7"
          >
            Read CONTRIBUTING.md
          </a>
        </div>
      </Reveal>

      <Reveal>
        <div className="mt-12 rounded-md border border-border/60 bg-bg-raised/40 p-6
                        text-sm text-text-dim">
          <p className="text-text">First time contributing to anything?</p>
          <p className="mt-2">
            That's fine. Open an issue with what you'd like to try and
            we'll pair you with someone on Discord (link incoming) to
            walk through your first PR end to end.
          </p>
        </div>
      </Reveal>
    </div>
  );
}
