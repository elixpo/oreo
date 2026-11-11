"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Reveal, fadeUp, staggerContainer } from "@/components/MotionWrap";
import { ArrowRight, Clock, ExternalLink, Github, Wrench } from "lucide-react";
import { HACKS, hackUrl } from "@/data/hacks";

const REPO = "https://github.com/elixpo/oreo";

const DIFF_TINT = {
  beginner:     { bg: "bg-teal/10",   text: "text-teal",   border: "border-teal/30" },
  intermediate: { bg: "bg-gold/10",   text: "text-gold",   border: "border-gold/30" },
  advanced:     { bg: "bg-lilac/10", text: "text-lilac", border: "border-lilac/30" },
};

export default function HacksPage() {
  return (
    <div className="relative">
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[520px] overflow-hidden">
        <div className="absolute left-1/3 top-0 h-[420px] w-[420px] rounded-full bg-gold/[0.10]  blur-[140px]" />
        <div className="absolute right-1/4 top-32 h-[260px] w-[260px] rounded-full bg-lilac/[0.10] blur-[120px]" />
        <div className="absolute left-1/4 top-48  h-[220px] w-[220px] rounded-full bg-teal/[0.08]  blur-[120px]" />
      </div>
      <div className="container-page pt-16 pb-28">
      <motion.div initial="hidden" animate="visible" variants={staggerContainer}>
        <motion.span variants={fadeUp} className="chip mb-6">
          <Wrench className="h-3 w-3" /> open hardware, open invitation
        </motion.span>
        <motion.h1
          variants={fadeUp}
          className="font-display text-4xl leading-[1.05] tracking-tight sm:text-5xl"
        >
          Customize Your Badge.{" "}
          <span className="bg-gradient-to-r from-primary via-gold to-lilac
                           bg-clip-text text-transparent">
            Make it weird.
          </span>
        </motion.h1>
        <motion.p variants={fadeUp} className="mt-5 max-w-2xl text-text-dim">
          Step-by-step recipes for putting your name, photos and colours on
          the badge, reading its sensors, and shipping your own updates.
          Each hack is one Markdown file in the repository, checked against
          the code.
        </motion.p>
      </motion.div>

      <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {HACKS.map((h, i) => {
          const t = DIFF_TINT[h.difficulty];
          const url = hackUrl(h);
          const external = /^https?:/.test(url);
          return (
            <motion.div
              key={h.slug}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: 0.04 * (i % 6), duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              whileHover={{ y: -4 }}
              className="card-surface group relative flex flex-col p-6 hover:border-primary/40"
            >
              <div className="mb-3 flex items-center justify-between gap-2">
                <h3 className="font-display text-lg leading-tight">
                  {/* The title link covers the whole card (after:inset-0). */}
                  <Link
                    href={url}
                    {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
                    className="after:absolute after:inset-0 after:content-['']"
                  >
                    {h.title}
                  </Link>
                </h3>
                <span className={`chip ${t.bg} ${t.text} ${t.border} border`}>
                  {h.difficulty}
                </span>
              </div>
              <p className="text-sm leading-relaxed text-text-dim">{h.body}</p>
              <div className="mt-auto flex items-center justify-between gap-3 pt-5 text-xs text-muted">
                <span className="inline-flex items-center gap-1.5">
                  <Clock className="h-3 w-3" />
                  {h.mins < 60 ? `${h.mins} min` : `${Math.round(h.mins / 60)} h`}
                </span>
                <span className="flex items-center gap-3">
                  {h.doc && (
                    <a
                      href={`${REPO}/blob/main/docs/hacks/${h.doc}`}
                      target="_blank" rel="noreferrer"
                      aria-label={`${h.title}: Markdown source on GitHub`}
                      className="relative z-10 inline-flex items-center gap-1 transition-colors hover:text-primary"
                    >
                      <Github className="h-3 w-3" /> source
                    </a>
                  )}
                  <span className="inline-flex items-center gap-1 transition-colors group-hover:text-primary">
                    {h.doc ? "Try this hack" : "Open"}
                    {external ? <ExternalLink className="h-3 w-3" /> : <ArrowRight className="h-3 w-3" />}
                  </span>
                </span>
              </div>
            </motion.div>
          );
        })}
      </div>

      <Reveal>
        <div className="mt-16 rounded-lg border border-border bg-bg-raised/40 p-8">
          <h2 className="font-display text-2xl">Got an idea for a hack?</h2>
          <p className="mt-2 text-text-dim">
            Propose it, then write it up as one Markdown file in{" "}
            <code className="text-text">docs/hacks/</code> and send a pull request.
            Once it is merged, it gets its own page here.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <a
              href={`${REPO}/issues/new?template=hack_proposal.yml`}
              target="_blank" rel="noreferrer"
              className="btn-primary"
            >
              Propose a hack
            </a>
            <a
              href={`${REPO}/blob/main/docs/hacks/README.md`}
              target="_blank" rel="noreferrer"
              className="btn-ghost"
            >
              <Github className="h-4 w-4" /> docs/hacks on GitHub
            </a>
          </div>
        </div>
      </Reveal>
      </div>
    </div>
  );
}
